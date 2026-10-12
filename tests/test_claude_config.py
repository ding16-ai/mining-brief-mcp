"""校验仓库根目录的 Claude Code 约定文件。

`.mcp.json` 是给 Claude Code 用的对外契约：路径写错、模块名改错、变量名拼错，
在客户端里只会表现为「server 连不上」，很难定位。所以这里按配置真连一遍。

`.claude/settings.json` 也有一个容易踩的坑：Claude Code **只查询 `Read` / `Edit`
的路径规则**，写成 `Write(...)` / `Glob(...)` 会被接受但永不生效，并在启动时报警告。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mining_brief.config import PROJECT_ROOT

MCP_CONFIG = PROJECT_ROOT / ".mcp.json"
CLAUDE_SETTINGS = PROJECT_ROOT / ".claude" / "settings.json"

# .mcp.json 里每个 server 必须至少暴露这些工具
EXPECTED_TOOLS: dict[str, set[str]] = {
    "mining-news": {"search", "fetch_article"},
    "mineral-pdf": {"extract_resources"},
    "lme-price": {"get_price", "get_trend"},
}

# Claude Code 的 ${VAR} / ${VAR:-default} 展开
_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        return os.environ.get(name, default or "")

    return _VAR_RE.sub(replace, value)


def _load_mcp_servers() -> dict[str, dict[str, Any]]:
    payload: dict[str, Any] = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    servers: dict[str, dict[str, Any]] = payload["mcpServers"]
    return servers


def _load_claude_settings() -> dict[str, Any]:
    settings: dict[str, Any] = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    return settings


def test_mcp_config_declares_exactly_the_three_servers() -> None:
    assert set(_load_mcp_servers()) == set(EXPECTED_TOOLS)


def test_mcp_config_matches_registered_server_modules() -> None:
    from mining_brief.servers import SERVER_MODULES

    declared = {entry["args"][-1] for entry in _load_mcp_servers().values()}
    registered = {f"mining_brief.servers.{name}_server" for name in SERVER_MODULES}
    assert declared == registered, "配置里的模块路径与 SERVER_MODULES 脱节了"


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
@pytest.mark.asyncio
async def test_server_starts_with_config_environment(name: str) -> None:
    entry = _load_mcp_servers()[name]
    # 配置里写的是 "python"，测试里换成当前解释器，避免依赖 PATH 上 python 的具体来源
    env = {**os.environ, **{key: _expand(val) for key, val in entry.get("env", {}).items()}}
    params = StdioServerParameters(command=sys.executable, args=list(entry["args"]), env=env)

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        exposed = {tool.name for tool in (await session.list_tools()).tools}

    assert EXPECTED_TOOLS[name] <= exposed, f"{name} 暴露的工具不全：{sorted(exposed)}"


def test_claude_settings_uses_only_supported_path_rule_tools() -> None:
    """路径规则只有 Read / Edit 会被查询，其他写法会被静默忽略并触发启动警告。"""
    permissions = _load_claude_settings()["permissions"]
    rules = list(permissions.get("allow", [])) + list(permissions.get("deny", []))
    offenders = [
        rule
        for rule in rules
        if rule.split("(")[0] in {"Write", "Glob", "MultiEdit", "NotebookEdit"}
    ]
    assert offenders == [], f"这些路径规则不会被 Claude Code 查询：{offenders}"


def test_env_file_is_protected_from_both_git_and_claude() -> None:
    """`.env` 里有 LLM API key，必须同时被 git 和 Claude Code 挡住。"""
    deny = _load_claude_settings()["permissions"]["deny"]
    assert any(rule.startswith("Read(./.env") for rule in deny), "Claude Code 未被禁止读取 .env"

    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored, ".env 没有被 gitignore"
    assert ".claude/settings.local.json" in ignored, "个人设置文件应被 gitignore"


def test_local_settings_file_is_not_tracked() -> None:
    """个人设置若被误提交，会覆盖队友的权限配置。"""
    local = PROJECT_ROOT / ".claude" / "settings.local.json"
    assert not local.exists() or _is_ignored(local), f"{local} 存在且未被忽略"


def _is_ignored(path: Path) -> bool:
    import subprocess

    result = subprocess.run(
        ["git", "check-ignore", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0
