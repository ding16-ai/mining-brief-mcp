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

pytest -q                                           # 全部测试（离线）
pytest --cov=mining_brief --cov-report=term-missing # 带覆盖率
ruff check . && ruff format .
mypy                                                # 严格模式，必须零问题
python scripts/make_fixtures.py                     # 重新生成离线 fixture

make check                                          # 上面几项一次跑完
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

## Claude Code 集成

仓库已按 Claude Code 的项目约定配好，克隆下来即可用：

| 文件 | 作用 |
| --- | --- |
| `.mcp.json` | 项目级 MCP server 配置（三个 server 都在里面）。用 `${VAR:-default}` 做变量展开，**不需要改绝对路径**；`LLM_API_KEY` 从环境变量取。首次使用需在 Claude Code 里批准（工作区信任）。 |
| `.claude/settings.json` | 项目共享权限：放行本项目自己的命令；禁读 `.env`、禁 `git push --force` / `git reset --hard` / `rm -rf`。 |
| `.claude/commands/verify.md` | `/verify` 斜杠命令，跑完整提交前自检。 |
| `.claude/agents/data-source-reviewer.md` | 数据来源审计子代理。改动 `servers/` 取数逻辑或 `fixtures/` 时用它复查「来源标注是否与实际取数路径一致」。 |
| `.claude/settings.local.json` | 个人设置，已在 `.gitignore` 中排除，**不要提交**。 |

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
8. **类型必须过 mypy strict**。新增代码不要用裸 `dict`、`Any` 或 `type: ignore` 逃逸；
   确实需要收窄时优先用 `cast` 并写明原因。CI 会拦。

## 代码风格

- 行宽 100，ruff 规则集 `E,F,I,UP,B,SIM`
- 公开函数写中文 docstring，说明「做什么」与「失败时怎样」
- 类型注解必须完整（mypy strict 强制），`from __future__ import annotations` 统一加在文件头
- 注释解释**为什么**，不解释**是什么**

## 新增一个 MCP server 的步骤

1. 在 `servers/` 新建 `xxx_server.py`，导出模块级 `mcp = FastMCP("xxx")` 与 `main()`
2. 把模块路径注册进 `servers/__init__.py` 的 `SERVER_MODULES`
3. 在 `mcp/claude_desktop_config.json` 补一段配置
4. 在 `docs/data-sources.md` 写清数据来源与局限
5. 在 `tests/test_servers_offline.py` 补一条工具形状断言

## 提交前自检

```bash
make check    # = ruff check + ruff format --check + mypy + pytest + 离线 selftest
```

四项全绿再提交。改动涉及打包时另跑 `make build`（会校验 fixture 是否打进 wheel）。

## CI

`.github/workflows/ci.yml` 三个 job：`lint`（ruff + mypy）、`test`（Python 3.10~3.13 矩阵）、
`build`（打包 + wheel 内 fixture 校验 + 装 wheel 后跑离线自检）。
本地用 `make ci` 复现。新增依赖记得同时更新 `pyproject.toml` 的上界。
