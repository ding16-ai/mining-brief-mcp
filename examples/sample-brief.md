# Pilbara 锂矿 日报（模板渲染）

> 简报对象：Pilbara 锂矿　｜　生成时间：2026-10-12 11:05
> 本简报由 AI 自动生成，仅供研究参考，**不构成任何投资建议**；储量数据须由合资格人士复核。

## 一、新闻摘要

- [[示例] Pilbara 锂矿项目发布季度运营更新](https://www.mining.com/)　`示例数据`
  - 占位内容：用于演示离线链路下的新闻摘要渲染。真实标题请在联网模式运行获取。
- [[示例] Pilbara 地区锂精矿现货价格区间震荡](https://www.mining.com/)　`示例数据`
  - 占位内容：用于演示价格类新闻的引用标注格式。
- [[示例] Pilbara 锂矿扩产项目进入可行性研究阶段](https://www.mining.com/)　`示例数据`
  - 占位内容：用于演示项目进展类新闻的渲染。

## 二、资源量（NI 43-101）

**项目**：Pilgangoora Operation (Pilbara Minerals, ASX: PLS)　**矿种**：lithium　**生效日期**：2025-06-11

| 类别 | 矿石量 (Mt) | 品位 | 金属量 |
| --- | ---: | ---: | ---: |
| Total | 446.00 | 1.280 % | 5.71 Mt Li2O |

_来源页：—　抽取置信度：0.60_

## 三、价格走势

- **lithium**　最新价：58.69 USD/份（2026-10-09）　⚠️ **代理指标，非官方报价**
  - 口径说明：无免费锂盐直连报价，使用 Global X 锂矿 ETF 作代理指标；数据来自内置示例 fixture，非真实行情
- **lithium**　近 30 天区间涨跌幅：-7.37%　⚠️ **代理指标，非官方报价**
  - 区间：2026-08-31 → 2026-10-09，共 30 个交易日

## 四、风险提示

- 价格数据为代理指标，可能与实际现货/期货价格存在显著偏离。
- 示例 fixture：仅含 2025-06-11 公告披露的 Measured+Indicated+Inferred 合计资源量（446 Mt @ 1.28% Li2O）。
- 未提供 Indicated / Inferred 拆分，实际使用时请从官方公告或 NI 43-101 全文抽取。
- contained_metal 为由 ore_mt × grade 推导的计算值，非公告原文数字。

## 数据降级说明

- 储量：未配置 MINING_BRIEF_DEFAULT_PDF，本次使用内置示例数据；请在 .env 中填入真实 NI 43-101 报告地址（公开报告见 SEDAR+）
- 价格：lithium 使用代理指标（无免费锂盐直连报价，使用 Global X 锂矿 ETF 作代理指标；数据来自内置示例 fixture，非真实行情）
- 价格：lithium 在线源不可用，已降级为内置示例 fixture，非真实行情
- 储量抽取：示例 fixture：仅含 2025-06-11 公告披露的 Measured+Indicated+Inferred 合计资源量（446 Mt @ 1.28% Li2O）。
- 储量抽取：未提供 Indicated / Inferred 拆分，实际使用时请从官方公告或 NI 43-101 全文抽取。
- 储量抽取：contained_metal 为由 ore_mt × grade 推导的计算值，非公告原文数字。
- 储量抽取：本次为 fixture:// 显式请求，返回内置示例数据，非真实抽取结果

## 引用来源

1. [示例数据](https://www.mining.com/)　`news`
2. [Pilgangoora Operation (Pilbara Minerals, ASX: PLS)](https://investorpa.com/announcement-pdf/20250611/147372.pdf)　`pdf`
