"""LLM 封装。只依赖 OpenAI 兼容协议，因此 DeepSeek / 通义 / 智谱 / 本地 vLLM 都能直接换。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, cast

from openai import OpenAI, omit
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from tenacity import retry, stop_after_attempt, wait_exponential

from mining_brief.config import Settings, get_settings

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMUnavailable(RuntimeError):
    """未配置 API key 或调用失败，调用方应降级到规则模式。"""


def _extract_json(text: str) -> dict[str, Any]:
    """容错地从模型输出里抠出 JSON 对象。

    依次尝试三种候选：整段文本 → ```json 代码块 → 首尾花括号之间的片段。
    全部失败（或解析出来不是对象）时抛 ``LLMUnavailable``，由调用方降级。
    """
    text = text.strip()
    candidates: list[str] = [text]

    block = _JSON_BLOCK.search(text)
    if block:
        candidates.append(block.group(1))

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        # 必须是对象：数组或标量都不是本模块的契约，直接跳过继续试下一个候选。
        if isinstance(data, dict):
            return data

    raise LLMUnavailable(f"模型输出不是合法 JSON 对象：{text[:200]}")


class LLM:
    """薄封装。所有方法在不可用时抛 LLMUnavailable，由上层决定降级。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: OpenAI | None = None

    @property
    def available(self) -> bool:
        return self.settings.llm_enabled

    @property
    def client(self) -> OpenAI:
        if not self.available:
            raise LLMUnavailable("未配置 LLM_API_KEY，已跳过模型调用")
        if self._client is None:
            self._client = OpenAI(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key,
                timeout=self.settings.http_timeout * 4,
            )
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8), reraise=True)
    def complete_json(self, system: str, user: str, *, temperature: float = 0.0) -> dict[str, Any]:
        """要求模型返回 JSON 对象。"""
        response = self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return _extract_json(content)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8), reraise=True)
    def complete_text(self, system: str, user: str, *, temperature: float = 0.3) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
    ) -> Any:
        """Agent 工具调用循环用。返回原始 message 对象，由 client 负责解析。

        messages / tools 由 client 按 OpenAI 线上格式构造，这里只做转交。
        用 ``cast`` 收窄到 SDK 的 TypedDict 类型而不是重建对象，是为了避免
        每次调用都多一层深拷贝；真正的形状由 ``MCPToolkit`` 保证。
        """
        response = self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=cast("list[ChatCompletionMessageParam]", messages),
            # 没有工具时显式省略该字段，比传 None 更安全：部分兼容网关不接受 null。
            # 用 SDK 的 omit 哨兵（类型为 Omit），而不是 NOT_GIVEN，否则类型对不上。
            tools=cast("list[ChatCompletionToolParam]", tools) if tools else omit,
            temperature=temperature,
        )
        return response.choices[0].message
