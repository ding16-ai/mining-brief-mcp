"""mining-brief-mcp —— 基于 MCP 协议的矿权日报 Agent。

包内分三层：

* ``mining_brief.servers``  —— 3 个 MCP server（news / pdf / price）
* ``mining_brief.agent``    —— Agent client：编排 MCP 工具 + LLM，产出 Markdown 简报
* ``mining_brief.cli``      —— 命令行入口
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
