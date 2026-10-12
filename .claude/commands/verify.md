---
description: 跑完整的提交前自检（ruff + 格式 + mypy + pytest + 离线端到端自检）
allowed-tools: Bash(make:*)
---

按顺序执行本项目的提交前自检，**任何一步失败就立刻停下来报告**，不要继续往下跑。

1. `make check` —— 等价于 `ruff check` + `ruff format --check` + `mypy` + `pytest` + 离线端到端自检
2. 若本次改动涉及打包相关文件（`pyproject.toml`、`src/` 布局、`fixtures/`），追加 `make build`

失败时逐条给出：

- 失败的检查项名称
- 原始报错（不要转述，直接贴关键行）
- 最小修复建议，以及这个修复是否会改变外部行为

**禁止为了让检查通过而放宽规则、加 `# noqa`、或删除/跳过测试。** 那属于掩盖问题，
本项目对这一点是零容忍的（见 `CLAUDE.md` 硬规则 2）。如果确实需要例外，
先说明理由并单独指出，由人来决定。
