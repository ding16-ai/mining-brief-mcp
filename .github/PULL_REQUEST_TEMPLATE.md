# Pull Request

## 这个 PR 做了什么

<!-- 一两句话说明改动内容与动机 -->

## 类型

- [ ] 修复 bug
- [ ] 新功能
- [ ] 重构（不改变外部行为）
- [ ] 文档
- [ ] 工程化 / CI

## 提交前自检

- [ ] `ruff check .` 通过
- [ ] `ruff format --check .` 通过
- [ ] `mypy` 通过
- [ ] `pytest` 通过
- [ ] `python -m mining_brief.cli --offline selftest` 通过

## 硬规则自查

详见 [`CLAUDE.md`](../CLAUDE.md)。请确认：

- [ ] **没有**让成文阶段使用 `evidence` 之外的数据
- [ ] **没有**新增静默吞异常的 `except`（降级必须写进 `Brief.degraded`）
- [ ] 若涉及价格数据，代理指标仍带 `is_proxy=true` 且成文有标注
- [ ] 若新增 fixture，带有 `fixture_note` 说明它是合成/占位数据
- [ ] 配置项只加在 `config.py` 与 `.env.example`
- [ ] 新增测试能在**离线**环境跑通（无外网、无 API key）
- [ ] **没有**改动 MCP 工具签名（`search` / `fetch_article` / `extract_resources` / `get_price` / `get_trend`）
      —— 若确实需要改动，请在此说明并同步更新 README 与客户端配置

## 补充说明

<!-- 需要评审重点关注的地方、已知取舍、后续待办 -->
