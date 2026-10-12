"""命令行入口。

mining-brief brief "生成一份关于 Pilbara 锂矿的今日简报"
mining-brief tools                 # 冒烟测试：列出 3 个 server 暴露的工具
mining-brief serve news|pdf|price  # 单独以 stdio 启动某个 MCP server
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from mining_brief.agent.client import MCPToolkit, run_agent
from mining_brief.config import PROJECT_ROOT, get_settings, reload_settings
from mining_brief.servers import SERVER_MODULES

DEFAULT_REQUEST = "生成一份关于 Pilbara 锂矿的今日简报"


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _apply_offline(flag: bool) -> None:
    if flag:
        os.environ["MINING_BRIEF_OFFLINE"] = "true"
        reload_settings()


async def _cmd_brief(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = args.request or DEFAULT_REQUEST
    out_path = Path(args.out) if args.out else PROJECT_ROOT / "out" / "brief.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    brief, markdown = await run_agent(request, use_llm=not args.no_llm)
    out_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print("-" * 72)
    print(f"已写入：{out_path}")
    print(
        f"LLM：{'启用' if settings.llm_enabled else '未配置（模板渲染）'}"
        f"　离线模式：{'是' if settings.offline else '否'}"
        f"　引用来源：{len(brief.citations)} 条"
        f"　降级项：{len(brief.degraded)} 条"
    )
    return 0


async def _cmd_tools(_: argparse.Namespace) -> int:
    async with MCPToolkit() as toolkit:
        if toolkit.failed_servers:
            for item in toolkit.failed_servers:
                print(f"[失败] {item}", file=sys.stderr)
        print(f"已连接 server：{', '.join(toolkit.server_names) or '（无）'}")
        for name in toolkit.tool_names:
            print(f"  - {name}")
        return 0 if toolkit.server_names else 1


async def _cmd_selftest(_: argparse.Namespace) -> int:
    """离线冒烟：不联网、不调模型，验证链路完整。"""
    _apply_offline(True)
    brief, markdown = await run_agent(DEFAULT_REQUEST, use_llm=False)
    ok = bool(brief.citations) and "引用来源" in markdown
    print(markdown)
    print("-" * 72)
    print(f"自检结果：{'通过' if ok else '未通过'}（引用 {len(brief.citations)} 条）")
    return 0 if ok else 1


def _cmd_serve(args: argparse.Namespace) -> int:
    module = SERVER_MODULES.get(args.name)
    if module is None:
        print(f"未知 server：{args.name}；可选 {', '.join(SERVER_MODULES)}", file=sys.stderr)
        return 2
    import importlib

    importlib.import_module(module).main()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mining-brief", description="基于 MCP 协议的矿权日报 Agent"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    parser.add_argument("--offline", action="store_true", help="强制离线，只读本地 fixture")
    sub = parser.add_subparsers(dest="command", required=True)

    p_brief = sub.add_parser("brief", help="生成一份日报")
    p_brief.add_argument("request", nargs="?", default=DEFAULT_REQUEST, help="自然语言请求")
    p_brief.add_argument("--out", default="", help="输出 Markdown 路径")
    p_brief.add_argument("--no-llm", action="store_true", help="跳过 LLM，使用模板渲染")

    sub.add_parser("tools", help="列出各 MCP server 暴露的工具")
    sub.add_parser("selftest", help="离线端到端冒烟测试")

    p_serve = sub.add_parser("serve", help="以 stdio 启动单个 MCP server")
    p_serve.add_argument("name", choices=sorted(SERVER_MODULES))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    _apply_offline(args.offline)

    handlers = {
        "brief": _cmd_brief,
        "tools": _cmd_tools,
        "selftest": _cmd_selftest,
    }
    if args.command == "serve":
        return _cmd_serve(args)
    return asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    raise SystemExit(main())
