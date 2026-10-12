# 架构说明

## 一句话

三个互相独立的 MCP server 各自封装一类数据源；一个 Agent client 通过 stdio 连上它们，
先取证、再成文，最后把每一步的来源写进 Markdown 简报。

## 分层

```
                     ┌──────────────────────────────┐
                     │  cli.py  /  docker compose   │
                     └──────────────┬───────────────┘
                                    │
                     ┌──────────────▼───────────────┐
                     │  agent/client.py             │
                     │  · MCPToolkit：拉起 3 个 server│
                     │  · 工具调用循环（LLM 驱动）    │
                     │  · 无 LLM 时的确定性取证路径   │
                     └──────────────┬───────────────┘
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
     ┌────────▼────────┐   ┌────────▼────────┐   ┌────────▼────────┐
     │ mining-news-mcp │   │ mineral-pdf-mcp │   │  lme-price-mcp  │
     │ search          │   │ extract_resources│   │ get_price       │
     │ fetch_article   │   │                 │   │ get_trend       │
     └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
              │                     │                     │
        RSS / HTML              PDF + LLM            公开行情接口
              └─────────────────────┼─────────────────────┘
                                    │
                          ┌─────────▼─────────┐
                          │  cache.py + net.py │
                          │  磁盘缓存 / 超时 /  │
                          │  离线开关 / UA      │
                          └─────────┬─────────┘
                                    │
                          ┌─────────▼─────────┐
                          │  fixtures/*.json   │
                          │  离线兜底，保证    │
                          │  demo 可复现        │
                          └───────────────────┘
```

## 关键设计决策

### 1. 取证与成文分离

工具调用阶段只负责拿数据，写入 `evidence` 字典；成文阶段（`agent/brief.py` 或
`prompts.BRIEF_SYSTEM`）**只允许使用 evidence 里的内容**。这样"模型编造数字"在架构上
被压到最低——成文阶段根本看不到原文以外的信息。

### 2. 三层降级，且降级可见

| 层级 | 失败场景 | 处理 |
| --- | --- | --- |
| 网络层 | 站点超时 / 反爬 / 限流 | `net.py` 抛异常 → server 内 `try/except` 捕获 |
| 数据层 | 在线源不可用 | 读 `fixtures/*.json` 兜底 |
| 模型层 | 未配 API key / 调用失败 | 走确定性模板渲染 |

所有降级都会写进 `Brief.degraded`，并在简报末尾的「数据降级说明」中展示。
**不静默吞异常**是这份代码的硬规则。

### 3. 代理指标必须显式标注

锂没有免费直连报价，`lme-price-mcp` 用 LIT ETF 作代理，返回 `is_proxy=true`
与 `note`；成文时强制标注「代理指标，非官方报价」。宁可难看，不可误导。

### 4. PDF 抽取先做页级预筛

NI 43-101 报告常见 200+ 页。整本丢给模型既贵又不准，所以先用关键词
（mineral resource / indicated / inferred / tonnes / grade）打分，只把 Top-4 页
送进模型。这一步把 token 成本降了两个数量级，同时提高了准确率。

### 5. 缓存即幂等

`cache.py` 以 URL/参数哈希为 key 落盘。重复跑同一份简报不会重复打网络，
也方便离线复现。缓存写失败不影响主流程。

## 扩展点

| 想做什么 | 改哪里 |
| --- | --- |
| 换 LLM（通义 / 智谱 / 本地 vLLM） | 只改 `.env` 的 `LLM_BASE_URL` / `LLM_MODEL` |
| 接真实付费行情源 | 在 `price_server.py` 新增 Provider，替换 `_series` 的取数分支 |
| 增加第 4 个数据源 | 在 `servers/` 加一个模块，注册进 `SERVER_MODULES` |
| 换成别的文档类型 | 复用 `pdf_server.py` 的「预筛 + LLM 结构化」模式 |

## 依赖版本策略：为什么锁 `mcp<2`

`mcp` 2.x 是一次破坏性升级：

| v1 | v2 |
| --- | --- |
| `mcp.server.fastmcp.FastMCP` | `mcp.server.mcpserver.MCPServer` |
| 客户端字段 camelCase（`isError` / `inputSchema`） | snake_case（`is_error` / `input_schema`） |
| `call_tool` 出错返回 `isError=True` | 改为抛 `MCPError` 异常 |
| 传输参数在构造函数上 | 移到 `run()` / `*_app()` |

生态（Claude Desktop、Cursor）与公开文档目前仍以 1.x 为主。本项目要保证
「新机器 5 分钟跑起来」，所以显式锁定 `mcp>=1.2,<2`。

将来迁移到 2.x 的改动面已经收敛在三处：`servers/*_server.py` 的 import 与
`mcp.run()` 调用、`agent/client.py` 里的 `call_tool` 返回值解析（已统一走
`structuredContent`，迁移时只需改字段名）、以及 `tool.input_schema`。

