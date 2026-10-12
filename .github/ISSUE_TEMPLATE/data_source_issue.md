---
name: Data source issue
about: 某个数据源不可用、口径不对或标注有误
title: "[Data] "
labels: ["data-source"]
---

## 涉及的 MCP server

- [ ] `mining-news-mcp`（新闻）
- [ ] `mineral-pdf-mcp`（NI 43-101 资源量）
- [ ] `lme-price-mcp`（价格）

## 具体问题

- [ ] 数据源不可用 / 返回错误
- [ ] 数据口径不对（例如把代理指标当成了现货价）
- [ ] 来源标注与实际取数路径不一致
- [ ] 降级没有在简报里体现
- [ ] 其他

## 复现命令

```bash
python -m mining_brief.cli brief "..."
```

## 观察到的输出

```
```

## 补充说明

<!-- 如果与价格有关，请注明品种、日期，以及期望的正确来源 -->
