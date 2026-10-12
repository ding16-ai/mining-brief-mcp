"""MCP server 的离线端到端测试。

这里刻意走**真实的 stdio 协议**（子进程 + MCP handshake），而不是直接 import 函数，
目的是同时验证：server 能启动、工具能被发现、schema 合法、返回值可 JSON 序列化。
"""

from __future__ import annotations

import pytest

from mining_brief.agent.client import MCPToolkit

EXPECTED_TOOLS = {
    "search",
    "fetch_article",
    "extract_resources",
    "get_price",
    "get_trend",
}


@pytest.mark.asyncio
async def test_three_servers_start_and_expose_tools():
    async with MCPToolkit() as toolkit:
        assert toolkit.failed_servers == [], f"server 启动失败：{toolkit.failed_servers}"
        assert toolkit.server_names == ["news", "pdf", "price"]
        assert EXPECTED_TOOLS.issubset(set(toolkit.tool_names))


@pytest.mark.asyncio
async def test_news_search_offline_falls_back_to_fixture():
    async with MCPToolkit() as toolkit:
        result = await toolkit.call("search", {"query": "Pilbara lithium", "days": 7})
    assert isinstance(result, list) and result, "离线模式应返回 fixture 中的示例新闻"
    assert {"title", "url", "source"} <= set(result[0])


@pytest.mark.asyncio
async def test_price_trend_offline_has_points_and_change():
    async with MCPToolkit() as toolkit:
        trend = await toolkit.call("get_trend", {"commodity": "锂", "days": 30})
    assert trend.get("commodity") == "lithium", "中文别名应被归一化"
    assert len(trend["points"]) > 0
    assert trend.get("change_pct") is not None


@pytest.mark.asyncio
async def test_price_unknown_commodity_returns_error_not_exception():
    async with MCPToolkit() as toolkit:
        result = await toolkit.call("get_price", {"commodity": "unobtainium"})
    assert "error" in result


@pytest.mark.asyncio
async def test_extract_resources_offline_returns_table_shape():
    async with MCPToolkit() as toolkit:
        table = await toolkit.call(
            "extract_resources", {"pdf_url": "https://example.com/ni43-101.pdf"}
        )
    assert "rows" in table and "warnings" in table
    assert table["warnings"], "离线降级必须留下可追溯的警告"
