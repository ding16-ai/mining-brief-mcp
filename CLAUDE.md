# CLAUDE.md

给 AI 协作者（Claude Code / 其他编码 Agent）的项目说明。改动代码前请先读完本文件。

## 项目是什么

基于 MCP 协议的矿权日报 Agent。三个 MCP server 各自封装一类数据源，一个 Agent client
连上它们，先取证、再成文，产出带引用来源的 Markdown 简报。

## 技术栈

- Python ≥ 3.10（开发环境 3.11/3.13）
- `mcp`（官方 SDK，FastMCP 写法）
- `pydantic` v2 —— 所有跨模块数据必须走模型，禁止裸 dict 满天飞
- `openai` SDK —— 走 OpenAI 兼容协议，默认指向 DeepSeek
- `pdfplumber` 抽 PDF 文本，`feedparser` 解析 RSS，`httpx` 发请求
- `pytest` + `pytest-asyncio`，`ruff` 做 lint/format

## 常用命令

```bash
pip install -e ".[dev]"

python -m mining_brief.cli --offline selftest       # 离线自检，改动后先跑这个
python -m mining_brief.cli brief "生成一份关于 Pilbara 锂矿的今日简报"
python -m mining_brief.cli tools                    # 列出各 server 的工具
python -m mining_brief.cli serve news|pdf|price     # 单独起一个 server

pytest -q
ruff check . && ruff format .
python scripts/make_fixtures.py                     # 重新生成离线 fixture
```

## 目录约定

```
src/mining_brief/
  config.py     # 唯一的配置读取点。新增环境变量必须加在这里 + .env.example
  models.py     # Pydantic 领域模型
  net.py        # 所有 HTTP 出口。禁止在别处直接 import httpx
  cache.py      # 磁盘缓存
  llm.py        # LLM 调用。所有方法在不可用时抛 LLMUnavailable
  servers/      # 一个文件一个 MCP server，导出 mcp 与 main()
  agent/        # client.py 编排、brief.py 渲染、prompts.py 提示词
  fixtures/     # 离线兜底数据，打包进 wheel
tests/          # 默认离线；需要联网的测试请显式标注
```

## 硬规则（改代码时不要破坏）

1. **取证与成文分离**。成文阶段只能使用 `evidence` 里的数据，不允许模型补充外部知识。
   提示词里的对应条款是 `prompts.BRIEF_SYSTEM` 第 1 条，不要删。
2. **降级必须可见**。任何数据源失败都要写进 `Brief.degraded`，禁止 `except: pass`。
   `except` 块里至少要 `logger.warning`。
3. **代理指标必须标注**。返回 `is_proxy=true` 的数据在简报里必须写明「代理指标，非官方报价」。
   锂价用 LIT ETF 代理是刻意选择，不要改成看起来更"准确"的假数据。
4. **不允许编造数据**。fixture 里不许放假的真实感数据；新增 fixture 必须带 `fixture_note`
   说明它是合成/占位数据。
5. **配置只在 `config.py` 读**。其他模块通过 `get_settings()` 取，不要直接 `os.getenv`。
6. **测试必须能离线跑**。CI 环境无外网、无 API key，新增测试不要依赖网络或模型。
7. **MCP 工具签名是契约**。`search` / `fetch_article` / `extract_resources` /
   `get_price` / `get_trend` 的名字与参数不可随意改动，README 与配置都依赖它们。

## 代码风格

- 行宽 100，ruff 规则集 `E,F,I,UP,B,SIM`
- 公开函数写中文 docstring，说明「做什么」与「失败时怎样」
- 类型注解尽量完整；`from __future__ import annotations` 统一加在文件头
- 注释解释**为什么**，不解释**是什么**

## 新增一个 MCP server 的步骤

1. 在 `servers/` 新建 `xxx_server.py`，导出模块级 `mcp = FastMCP("xxx")` 与 `main()`
2. 把模块路径注册进 `servers/__init__.py` 的 `SERVER_MODULES`
3. 在 `mcp/claude_desktop_config.json` 补一段配置
4. 在 `docs/data-sources.md` 写清数据来源与局限
5. 在 `tests/test_servers_offline.py` 补一条工具形状断言

## 提交前自检

```bash
ruff check . && pytest -q && python -m mining_brief.cli --offline selftest
```

三项全绿再提交。
