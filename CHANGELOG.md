# Changelog

本文件记录项目的所有重要变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- **GitHub Actions CI**：Python 3.10 / 3.11 / 3.12 / 3.13 矩阵，依次执行 ruff check、
  ruff format --check、mypy、pytest（含覆盖率）、离线端到端自检与打包校验。
- **mypy 严格模式**（`strict = true`），覆盖 `src` / `tests` / `scripts`，零类型问题。
- **单元测试层**：新增 `tests/test_core_units.py` 与 `tests/test_servers_units.py`，
  直接覆盖此前只能靠子进程间接触达的边界分支。测试数 15 → 66，覆盖率 36% → 65%。
- **覆盖率门槛** `fail_under = 60`，在 CI 中强制。
- **打包校验脚本** `scripts/check_wheel.py`：确认 fixture 数据确实被打进 wheel。
- `.pre-commit-config.yaml`、`.editorconfig`、`.dockerignore`、`LICENSE`（MIT）。
- `.github/ISSUE_TEMPLATE/` 与 `.github/PULL_REQUEST_TEMPLATE.md`。

### 变更

- **依赖统一加上版本上界**，避免上游发布大版本后破坏「克隆下来就能跑」的承诺。
- `llm._extract_json` 改为按候选列表依次尝试，并显式拒绝非对象 JSON
  （此前若模型返回数组会被原样透传，破坏函数签名承诺）。
- `net.get_json` 在返回前校验响应确为 JSON 对象，不再把 `Any` 一路传下去。
- `pdf_server._load_fixture` 不再可能抛异常：fixture 缺失、JSON 损坏、顶层非对象
  三种情况统一返回空表并留下 warning —— 它位于降级路径上，自身必须可靠。
- `pyproject.toml` 增加 classifiers 与 `[project.urls]`。

### 修复

- `news_server._to_iso` 中 `datetime(*parsed[:6], tzinfo=timezone.utc)` 存在参数冲突隐患
  （feedparser 给的是 9 元组 `struct_time`，位置参数可能撞上 `tzinfo`），改为显式解包。
- `cache.cached` 的 `type: ignore[return-value]` 覆盖的错误码不匹配，改用 `cast` 表达意图。
- `news_server._load_fixture` 现在会剔除非字典条目，避免 fixture 里混入脏数据时崩溃。

## [0.1.0] - 2026-10-12

### 新增

- 三个互相独立的 MCP server：
  - `mining-news-mcp`：`search(query, days)` / `fetch_article(url)`
  - `mineral-pdf-mcp`：`extract_resources(pdf_url)`
  - `lme-price-mcp`：`get_price(commodity, date)` / `get_trend(commodity, days)`
- Agent client：LLM 驱动的工具调用取证 → 基于证据成文 → 一轮自审（评分 <8 则重写）。
- **取证与成文分离**：成文阶段只能看到 evidence JSON，从架构上抑制模型编造数字。
- **三层降级**（网络层 / 数据层 / 模型层），所有降级写入 `Brief.degraded` 并在简报末尾展示。
- **代理指标显式标注**：锂价用 LIT ETF 代理，返回 `is_proxy=true`，成文强制标注。
- **来源标注与实际取数路径一致**：降级到 fixture 时 `source` 写明 `fixture（在线源不可用）`。
- **PDF 页级预筛**：按关键词把 200+ 页缩到 Top-4 页再送模型。
- 离线模式与内置 fixture，保证无外网、无 API key 时链路仍可复现。
- Dockerfile / docker-compose / Makefile，目标为新机器 5 分钟跑出第一份简报。
- `docs/architecture.md`（含「为什么锁 mcp<2」）与 `docs/data-sources.md`（含代理指标与已知局限）。
- 离线测试 15 项：走真实 stdio 协议验证 server 启动、工具发现与降级路径。

[Unreleased]: https://github.com/ding16-ai/mining-brief-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ding16-ai/mining-brief-mcp/releases/tag/v0.1.0
