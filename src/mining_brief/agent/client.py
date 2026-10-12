"""Agent client：拉起 3 个 MCP server，编排「取证 → 成文 → 自审」流程。

设计要点
--------
* **取证与成文分离**：工具调用只负责拿数据，成文只允许使用拿到的数据。
  这样「模型编造数字」的问题在架构层面被压到最低。
* **两档运行模式**：配了 LLM_API_KEY 走完整 Agent 流程；没配则走确定性模板渲染，
  demo 依然可跑，只是文风朴素 —— 但同样不会编造内容。
* **降级可见**：任何数据源失败都写进 ``Brief.degraded`` 并在简报末尾展示，不静默吞掉。
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from contextlib import AsyncExitStack
from datetime import datetime
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mining_brief.agent import prompts
from mining_brief.agent.brief import (
    build_citations,
    dedupe,
    default_title,
    evidence_to_prompt_block,
    fallback_brief,
)
from mining_brief.config import PROJECT_ROOT, Settings, get_settings
from mining_brief.llm import LLM
from mining_brief.models import Brief, today_iso
from mining_brief.servers import SERVER_MODULES

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
MAX_REVISE_ROUNDS = 2
SRC_DIR = PROJECT_ROOT / "src"

_SUBJECT_RE = re.compile(r"关于(.+?)的")


class MCPToolkit:
    """以 stdio 方式拉起全部 MCP server，暴露统一的工具发现与调用接口。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tool_owner: dict[str, str] = {}
        self._schemas: list[dict[str, Any]] = []
        self.failed_servers: list[str] = []

    async def __aenter__(self) -> MCPToolkit:
        env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}
        for name, module in SERVER_MODULES.items():
            params = StdioServerParameters(command=sys.executable, args=["-m", module], env=env)
            try:
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                listing = await session.list_tools()
            except Exception as exc:  # noqa: BLE001
                logger.error("MCP server %s 启动失败：%s", name, exc)
                self.failed_servers.append(f"{name}: {exc}")
                continue

            self._sessions[name] = session
            for tool in listing.tools:
                self._tool_owner[tool.name] = name
                self._schemas.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                        },
                    }
                )
            logger.info("MCP server %s 已连接，暴露 %d 个工具", name, len(listing.tools))
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    @property
    def server_names(self) -> list[str]:
        return sorted(self._sessions)

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tool_owner)

    def openai_tools(self) -> list[dict[str, Any]]:
        return list(self._schemas)

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        owner = self._tool_owner.get(name)
        if owner is None:
            raise KeyError(f"未知工具 {name}；已注册：{self.tool_names}")
        result = await self._sessions[owner].call_tool(name, arguments)

        # FastMCP 对「返回非 dict」的工具会包一层 {"result": <value>}，
        # 这里统一拆掉，保证调用方拿到的就是工具真正的返回值。
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            if isinstance(structured, dict) and set(structured) == {"result"}:
                return structured["result"]
            return structured

        chunks = [getattr(block, "text", "") for block in (result.content or [])]
        raw = "\n".join(chunk for chunk in chunks if chunk).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def extract_subject(request: str) -> str:
    match = _SUBJECT_RE.search(request)
    if match:
        return match.group(1).strip()
    match = re.search(r"about\s+(.+)", request, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(".。")
    return "Pilbara 锂矿"


def _empty_evidence(subject: str) -> dict[str, Any]:
    return {
        "subject": subject,
        "news": [],
        "articles": [],
        "resource": {},
        "quote": {},
        "trend": {},
        "degraded": [],
    }


def _route_result(evidence: dict[str, Any], tool: str, args: dict[str, Any], result: Any) -> None:
    """把工具返回值归档进证据包，并记录降级信息。"""
    if isinstance(result, dict) and result.get("error"):
        evidence["degraded"].append(f"{tool}({args}) 失败：{result['error']}")
        return

    if tool == "search" and isinstance(result, list):
        evidence["news"] = result
    elif tool == "fetch_article" and isinstance(result, dict):
        evidence["articles"].append(result)
    elif tool == "extract_resources" and isinstance(result, dict):
        evidence["resource"] = result
        for warning in result.get("warnings") or []:
            evidence["degraded"].append(f"储量抽取：{warning}")
        if not result.get("rows"):
            evidence["degraded"].append("储量抽取：未取得任何资源量行")
    elif tool == "get_price" and isinstance(result, dict):
        evidence["quote"] = result
        _note_price_degradation(evidence, result)
    elif tool == "get_trend" and isinstance(result, dict):
        evidence["trend"] = result
        _note_price_degradation(evidence, result)


def _note_price_degradation(evidence: dict[str, Any], result: dict[str, Any]) -> None:
    """价格数据的两种问题都要显式记录：代理指标、以及降级到 fixture。"""
    commodity = result.get("commodity")
    if result.get("is_proxy"):
        evidence["degraded"].append(f"价格：{commodity} 使用代理指标（{result.get('note', '')}）")
    if str(result.get("source", "")).startswith("fixture"):
        evidence["degraded"].append(
            f"价格：{commodity} 在线源不可用，已降级为内置示例 fixture，非真实行情"
        )


async def _collect_with_llm(
    toolkit: MCPToolkit, llm: LLM, request: str, evidence: dict[str, Any]
) -> str:
    """LLM 工具调用循环。返回模型的收尾文本。"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompts.AGENT_SYSTEM},
        {"role": "user", "content": request},
    ]
    tools = toolkit.openai_tools()
    final_text = ""

    for round_no in range(1, MAX_TOOL_ROUNDS + 1):
        message = llm.complete_with_tools(messages, tools)
        tool_calls = getattr(message, "tool_calls", None) or []

        if not tool_calls:
            final_text = message.content or ""
            logger.info("Agent 第 %d 轮结束取证，无更多工具调用", round_no)
            break

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ],
            }
        )

        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = await toolkit.call(name, args)
            except Exception as exc:  # noqa: BLE001
                result = {"error": str(exc)}
                logger.warning("工具 %s 调用失败：%s", name, exc)
            _route_result(evidence, name, args, result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False)[:8000],
                }
            )
    else:
        final_text = "（已达工具调用轮次上限）"

    return final_text


async def _collect_deterministic(
    toolkit: MCPToolkit, subject: str, evidence: dict[str, Any]
) -> None:
    """无 LLM 时的固定取证路径：新闻 + 锂价走势 + 储量（若配置了默认 PDF）。"""
    settings = get_settings()
    plan: list[tuple[str, dict[str, Any]]] = [
        ("search", {"query": subject, "days": 7}),
        ("get_trend", {"commodity": "lithium", "days": 30}),
        ("get_price", {"commodity": "lithium"}),
    ]

    if settings.default_pdf_url:
        plan.append(("extract_resources", {"pdf_url": settings.default_pdf_url}))
    else:
        # 用 fixture:// 显式声明"我要示例数据"，而不是拿一个假 URL 去发真实请求。
        plan.append(("extract_resources", {"pdf_url": "fixture://resources_pilbara"}))
        evidence["degraded"].append(
            "储量：未配置 MINING_BRIEF_DEFAULT_PDF，本次使用内置示例数据；"
            "请在 .env 中填入真实 NI 43-101 报告地址（公开报告见 SEDAR+）"
        )

    for name, args in plan:
        try:
            result = await toolkit.call(name, args)
        except Exception as exc:  # noqa: BLE001
            result = {"error": str(exc)}
        _route_result(evidence, name, args, result)


def _render_with_llm(llm: LLM, evidence: dict[str, Any], subject: str) -> tuple[str, list[str]]:
    """让模型基于证据渲染 Markdown，并做一轮自审。"""
    block = evidence_to_prompt_block(evidence)
    draft = llm.complete_text(
        prompts.BRIEF_SYSTEM,
        f"简报对象：{subject}\n生成日期：{today_iso()}\n\n证据 JSON：\n{block}",
    )

    notes: list[str] = []
    for _ in range(MAX_REVISE_ROUNDS):
        try:
            review = llm.complete_json(
                prompts.REVISE_SYSTEM, f"草稿：\n{draft}\n\n证据 JSON：\n{block}"
            )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"自审失败：{exc}")
            break
        score = int(review.get("score") or 0)
        issues = [str(i) for i in (review.get("issues") or [])]
        if review.get("ok") and score >= 8:
            notes.append(f"自审通过，评分 {score}/10")
            break
        notes.append(f"自审未通过（{score}/10）：{'; '.join(issues[:3])}")
        draft = llm.complete_text(
            prompts.BRIEF_SYSTEM,
            "以下草稿被审稿人指出问题，请修正后重新输出完整 Markdown：\n"
            f"问题：{'; '.join(issues)}\n\n原草稿：\n{draft}\n\n证据 JSON：\n{block}",
        )
    return draft, notes


async def run_agent(
    request: str,
    *,
    settings: Settings | None = None,
    use_llm: bool = True,
) -> tuple[Brief, str]:
    """执行一次简报生成。

    Returns:
        (Brief, markdown 文本)
    """
    settings = settings or get_settings()
    subject = extract_subject(request)
    evidence = _empty_evidence(subject)
    llm = LLM(settings)

    async with MCPToolkit(settings) as toolkit:
        for item in toolkit.failed_servers:
            evidence["degraded"].append(f"MCP server 启动失败 — {item}")

        if use_llm and llm.available:
            try:
                await _collect_with_llm(toolkit, llm, request, evidence)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM 取证失败，回退确定性路径：%s", exc)
                evidence["degraded"].append(f"LLM 取证失败，已回退确定性路径：{exc}")
                await _collect_deterministic(toolkit, subject, evidence)
        else:
            if use_llm and not llm.available:
                evidence["degraded"].append("未配置 LLM_API_KEY，使用确定性模板渲染")
            await _collect_deterministic(toolkit, subject, evidence)

    has_evidence = bool(evidence["news"] or evidence["resource"] or evidence["trend"])
    if use_llm and llm.available and has_evidence:
        try:
            markdown, notes = _render_with_llm(llm, evidence, subject)
            evidence["degraded"].extend(notes)
            brief = Brief(
                title=default_title(subject),
                subject=subject,
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                citations=build_citations(evidence),
                degraded=dedupe(evidence["degraded"]),
                news_section="",
                resource_section="",
                price_section="",
                risk_section="",
            )
            return brief, markdown
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 成文失败，回退模板渲染：%s", exc)
            evidence["degraded"].append(f"LLM 成文失败，已回退模板渲染：{exc}")

    brief = fallback_brief(evidence, subject)
    from mining_brief.agent.brief import render_markdown

    return brief, render_markdown(brief)
