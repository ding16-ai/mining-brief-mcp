"""三个 MCP server 的包。每个模块都可独立以 stdio 方式启动：

python -m mining_brief.servers.news_server
python -m mining_brief.servers.pdf_server
python -m mining_brief.servers.price_server
"""

SERVER_MODULES = {
    "news": "mining_brief.servers.news_server",
    "pdf": "mining_brief.servers.pdf_server",
    "price": "mining_brief.servers.price_server",
}

__all__ = ["SERVER_MODULES"]
