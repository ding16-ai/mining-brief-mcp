# mining-brief-mcp

[![CI](https://github.com/ding16-ai/mining-brief-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ding16-ai/mining-brief-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

基于 **MCP（Model Context Protocol）** 的矿权日报 Agent：输入一句自然语言，自动取证并产出一份带引用来源的 Markdown 简报。

```
输入：生成一份关于 Pilbara 锂矿的今日简报
输出：news summary + reserve data + price trend + risk hints + 引用源链接
```

> 示例产出：[`examples/sample-brief.md`](examples/sample-brief.md)

## 三个 MCP server

| Server | 工具 | 职责 |
| --- | --- | --- |
| `mining-news-mcp` | `search(query, days=7)`<br>`fetch_article(url)` | 矿业新闻检索与正文抓取 |
| `mineral-pdf-mcp` | `extract_resources(pdf_url)` | 从 NI 43-101 技术报告抽 Indicated / Inferred 资源量 |
| `lme-price-mcp` | `get_price(commodity, date=None)`<br>`get_trend(commodity, days=30)` | 大宗商品报价与走势 |

外加一个 **Agent client**（`agent/client.py`）：通过 stdio 连上三个 server，
用 LLM 驱动工具调用循环完成取证，再基于证据渲染简报。

## 快速开始（5 分钟）

```bash
git clone https://github.com/ding16-ai/mining-brief-mcp.git && cd mining-brief-mcp

python -m venv .venv
source .venv/Scripts/activate      # Windows；Linux/macOS 用 .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env               # 填入 LLM_API_KEY（可留空，见下文）

# 1) 先跑离线自检：不联网、不调模型，验证链路完整
python -m mining_brief.cli --offline selftest

# 2) 生成一份真实简报
python -m mining_brief.cli brief "生成一份关于 Pilbara 锂矿的今日简报"
```

或者用 Docker：

```bash
cp .env.example .env
docker compose up --build
```

生成的简报默认写到 `out/brief.md`。
想看预期产出长什么样，直接读 [`examples/sample-brief.md`](examples/sample-brief.md)（离线模式生成）。

## 运行模式

| 模式 | 触发条件 | 行为 |
| --- | --- | --- |
| **完整 Agent** | 配了 `LLM_API_KEY` | LLM 驱动工具调用取证 → 基于证据成文 → 自审一轮（评分 <8 则重写） |
| **无模型** | 未配 key，或加 `--no-llm` | 走固定取证路径 + 模板渲染。**依然不编造内容** |
| **离线** | `--offline` 或 `MINING_BRIEF_OFFLINE=true` | 不发任何网络请求，全部读 `src/mining_brief/fixtures/` |

三种模式产出的简报结构一致，差别只在文风与数据新鲜度。

## 常用命令

```bash
python -m mining_brief.cli brief "..."   # 生成简报
python -m mining_brief.cli tools         # 冒烟测试：列出各 server 暴露的工具
python -m mining_brief.cli selftest      # 离线端到端自检
python -m mining_brief.cli serve news    # 单独启动某个 MCP server（stdio）
python -m mining_brief.cli --help

make test      # 运行测试
make cov       # 运行测试并统计覆盖率
make lint      # ruff 静态检查 + 格式检查
make typecheck # mypy 严格模式
make check     # 提交前全量自检（lint + typecheck + test + 离线自检）
make ci        # 本地复现 CI（check + 打包校验）
```

## 目录结构

```
mining-brief-mcp/
├── src/mining_brief/
│   ├── config.py            # 唯一的配置读取点
│   ├── models.py            # Pydantic 领域模型
│   ├── net.py               # HTTP 收口：超时 / UA / 离线开关
│   ├── cache.py             # 磁盘缓存（按 URL 哈希）
│   ├── llm.py               # OpenAI 兼容封装（默认 DeepSeek）
│   ├── servers/             # 3 个 MCP server
│   │   ├── news_server.py
│   │   ├── pdf_server.py
│   │   └── price_server.py
│   ├── agent/
│   │   ├── client.py        # MCPToolkit + 取证编排
│   │   ├── brief.py         # Markdown 渲染
│   │   └── prompts.py       # 全部提示词
│   └── fixtures/            # 离线兜底数据
├── tests/                   # 离线测试（不联网、不调模型）
├── docs/
│   ├── architecture.md      # 架构与设计决策
│   └── data-sources.md      # 数据源、代理指标与已知局限
├── mcp/claude_desktop_config.json
├── scripts/make_fixtures.py
├── Dockerfile / docker-compose.yml / Makefile
└── CLAUDE.md
```

## 工程化

| 维度 | 做法 |
| --- | --- |
| **包结构** | `src/` 布局，`pip install -e .` 可安装，`mining-brief` 命令行入口 |
| **静态检查** | `ruff check`（规则集 `E,F,I,UP,B,SIM`，行宽 100）+ `ruff format --check` |
| **类型检查** | `mypy --strict`，覆盖 `src` / `tests` / `scripts`，**零问题** |
| **测试** | 66 项，**全部离线可跑**（不联网、不调模型）；单元测试 + 真实 stdio 集成测试 |
| **覆盖率** | 65%，CI 中强制 `fail_under = 60` |
| **CI** | GitHub Actions：Python 3.10/3.11/3.12/3.13 矩阵，lint → typecheck → test → 离线自检 → 打包校验 |
| **依赖管理** | 全部依赖带版本上界；`mcp` 显式锁 `<2`（原因见 `docs/architecture.md`） |
| **提交钩子** | `.pre-commit-config.yaml`（ruff + mypy + 通用文件检查 + 私钥检测） |
| **容器化** | `Dockerfile` + `docker-compose.yml`，`docker compose up --build` 一键起 |
| **文档** | 架构决策、数据源与已知局限、CHANGELOG、CLAUDE.md（AI 协作者约定） |
| **协作** | Issue 模板（bug / feature / 数据源问题）、PR 模板（含硬规则自查清单） |
| **AI 协作约定** | `CLAUDE.md` + `.mcp.json` + `.claude/`（共享权限、`/verify` 命令、数据来源审计子代理） |

提交前跑一条命令即可对齐 CI：

```bash
make check    # lint + typecheck + test + 离线自检
```

## 设计要点

- **取证与成文分离** —— 成文阶段只能看到证据，从架构上抑制模型编造数字。
- **降级可见** —— 任何数据源失败都写进简报末尾的「数据降级说明」，不静默吞异常。
- **来源标注与实际取数路径一致** —— 在线取数失败降级到 fixture 时，`source` 会写成
  `fixture（在线源不可用）`，不会继续挂上游站点的名义。
- **代理指标显式标注** —— 锂价用 LIT ETF 代理，返回 `is_proxy=true`，成文强制标注。
- **PDF 页级预筛** —— 先按关键词把 200+ 页缩到 Top-4 页再送模型，成本降两个数量级。
- **无 key 也能跑** —— 未配置模型时走确定性模板，demo 不因缺 key 而失败。

详见 [`docs/architecture.md`](docs/architecture.md)（含依赖版本策略：为什么锁 `mcp<2`）。

## 已知局限

⚠️ **请先读 [`docs/data-sources.md`](docs/data-sources.md)。** 摘要：

- **锂价是代理指标**（LIT ETF），不是碳酸锂现货价，不能直接用于定价。
- LME / SHFE / 上海钢联的官方行情需商业授权，本项目未直连。
- `fixtures/` 中的价格序列是**合成数据**，新闻是**占位内容**，仅用于离线演示。
- NI 43-101 的复杂表格存在错位风险，抽取结果**须由合资格人士（QP）复核**。

## 在 Claude Code 中使用

仓库根目录已带 `.mcp.json`，**不需要改任何路径** —— 三个 server 全部通过
`${VAR:-default}` 做变量展开，`LLM_API_KEY` 直接从环境变量取。

```bash
pip install -e ".[dev]"     # 先装依赖（也可跳过，.mcp.json 会兜底设 PYTHONPATH）
claude                      # 在仓库根目录启动，首次会提示批准项目级 MCP server
```

批准后可直接对话调用，或用仓库自带的两个约定：

- `/verify` —— 跑完整提交前自检（ruff + 格式 + mypy + pytest + 离线自检）
- `data-source-reviewer` 子代理 —— 复查「来源标注是否与实际取数路径一致」，
  改动 `servers/` 取数逻辑或 `fixtures/` 时值得跑一遍

项目约定写在 [`CLAUDE.md`](CLAUDE.md)，权限与安全边界在
[`.claude/settings.json`](.claude/settings.json)（禁读 `.env`、禁 `git push --force` 等）。

## 在 Claude Desktop / Cursor 中使用

这两个客户端不支持 `.mcp.json`，需要手动合并：把
[`mcp/claude_desktop_config.json`](mcp/claude_desktop_config.json) 里的 `mcpServers`
合并进你的客户端配置，并把绝对路径替换成实际路径。重启客户端后即可直接对话调用这三个 server。

## 免责声明

本项目为工程演示，输出内容由 AI 生成，**不构成任何投资建议**，也不构成储量认定的法律依据。

## License

MIT
