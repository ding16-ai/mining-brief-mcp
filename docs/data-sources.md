# 数据源说明与已知局限

写这份文档的目的：**让评审一眼看清哪些数据是真的、哪些是代理、哪些是示例。**

## 一、新闻（mining-news-mcp）

| 优先级 | 源 | 说明 |
| --- | --- | --- |
| 1 | Google News RSS | `https://news.google.com/rss/search?q=<query>`，无需 key，覆盖面广 |
| 2 | mining.com 官方 RSS | `https://www.mining.com/feed/`，矿业垂直媒体 |
| 3 | 本地 fixture | `fixtures/news_pilbara.json`，**占位内容**，仅用于离线演示 |

局限：

- Google News RSS 的 `source` 字段有时为空，此时回填为 "Google News"。
- RSS 只给摘要，正文需 `fetch_article(url)` 二次抓取；部分站点有反爬，会返回 `error`。
- 未做去重与事件聚类，同一事件可能出现在多条结果中。

## 二、资源量（mineral-pdf-mcp）

抽取链路：下载 PDF → pdfplumber 取页文本 → 关键词预筛 Top-4 页 → 强模型结构化 → Pydantic 校验 + 单位归一。

| 项目 | 说明 |
| --- | --- |
| 支持输入 | `http(s)://`、本地绝对路径、`file://` |
| 单位归一 | 矿石量统一为 Mt（tonnes ÷ 1e6，kt ÷ 1e3） |
| 置信度 | 模型自评 `confidence`（0~1）；无有效行时强制 ≤ 0.2 |
| 失败处理 | 记录 `warnings`，`rows` 返回空，**绝不编造** |

已知局限：

- **表格错位**：NI 43-101 的资源量表常为多级表头（类别 × 品位档 × 金属量），
  纯文本抽取后列对齐容易丢失，可能把品位与金属量串位。已在 prompt 中要求
  "找不到就填 null"，但复杂表仍需人工复核。
- **单位歧义**：原文若混用 `Mt` / `kt` / `tonnes`，存在误读风险。
- **口径差异**：`Measured+Indicated` 与 `Inferred` 不能简单相加作为"总资源量"，
  简报中已按类别分列。
- **扫描件**：纯图片型 PDF 无文本层，pdfplumber 取不到内容，会走到"未定位到资源量表格"分支。

> ⚠️ 本工具只做信息抽取，**不构成任何投资建议**。储量数据须由合资格人士（QP）复核，
> 并以其签署的 NI 43-101 技术报告为准。

### 关于内置 fixture

`fixtures/resources_pilbara.json` 取自 Pilbara Minerals（ASX: PLS）2025-06-11 资源量更新
公告披露的 **Measured + Indicated + Inferred 合计**（446 Mt @ 1.28% Li₂O）。

它**只含合计值，不含 Indicated / Inferred 拆分**，且 `contained_metal` 是由
`ore_mt × grade` 推导的计算值。真实使用时请替换为从公告或 NI 43-101 全文抽取的结果。

## 三、价格（lme-price-mcp）

**这是本项目最大的数据局限，必须说清楚。**

LME / SHFE / 上海钢联的官方行情需要商业授权或登录，无法在开源 demo 中直连。
因此采取「可插拔 Provider + 代理指标」策略：

| 品种 | 在线取数 | 是否代理 | 说明 |
| --- | --- | --- | --- |
| copper | Yahoo `HG=F` | 否 | COMEX 铜期货主力合约 |
| zinc | Yahoo `ZN=F` | 否 | COMEX 锌期货主力合约 |
| gold | Yahoo `GC=F` | 否 | COMEX 黄金期货主力合约 |
| nickel | Yahoo `NI=F` | 否 | COMEX 镍期货主力合约 |
| iron_ore | Yahoo `TIO=F` | **是** | SGX 铁矿石掉期，代理普氏指数 |
| lithium | Yahoo `LIT` | **是** | Global X 锂矿 ETF，代理锂盐价格 |
| cobalt | 无在线源 | **是** | 直接使用 fixture 基准值 |

局限：

- Yahoo 的 `chart` 接口是公开但非官方承诺的接口，**随时可能变更、限流或直接 403**。
  实测在部分网络/地区会返回 `429` 或 `403`；代码会依次尝试 `query1` / `query2`
  两个入口，全部失败才降级到 fixture。
- 降级后 `source` 会写成 `fixture（在线源不可用）` 且 `source_url` 为空，
  **不会继续挂 Yahoo 的名义** —— 来源标注必须与实际取数路径一致，这是本项目的硬规则。
- **代理指标不能当作现货价使用**。`LIT` 是股票 ETF，受权益市场情绪影响，
  与碳酸锂现货价格可能长期背离。
- 未做汇率换算，`currency` 固定为 USD。
- fixture 中的价格序列是**合成数据**，仅用于离线演示链路，不是历史行情。

### 试过但不采用的源

| 源 | 结果 |
| --- | --- |
| `stooq.com/q/d/l/` | 返回 JS 挑战页而非 CSV，无法在无浏览器环境使用 |
| 上海钢联 / SMM 公开页 | 需登录，且条款禁止自动抓取 |
| Alpha Vantage / FMP | 需要 API key，与"开箱即用"目标冲突 |

如果要接入真实付费行情源，在 `price_server.py` 里加一个 Provider 并替换
`_series()` 的取数分支即可，Agent 侧代码无需改动。

## 四、合规与使用边界

- 抓取公开页面时遵守目标站点 `robots.txt` 与使用条款；已设置可识别的 `User-Agent`。
- 缓存到 `data/cache/` 与 `data/pdfs/` 的内容仅用于本地复现，请勿二次分发受版权保护的报告。
- 本项目输出为**研究与工程演示**用途，不构成投资建议、不构成储量认定的法律依据。
