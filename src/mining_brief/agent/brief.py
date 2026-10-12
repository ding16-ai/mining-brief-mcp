"""把证据渲染成 Markdown 简报（含引用清单与降级说明）。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from mining_brief.models import Brief, Citation, today_iso


def evidence_to_prompt_block(evidence: dict[str, Any]) -> str:
    """证据 -> 交给模型的紧凑 JSON。"""
    return json.dumps(evidence, ensure_ascii=False, indent=2)


def build_citations(evidence: dict[str, Any]) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[str] = set()

    for article in evidence.get("news") or []:
        url = article.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        citations.append(Citation(label=article.get("source") or "news", url=url, kind="news"))

    resource = evidence.get("resource") or {}
    pdf_url = resource.get("source_url") or ""
    if pdf_url and pdf_url not in seen:
        seen.add(pdf_url)
        citations.append(
            Citation(
                label=resource.get("project") or "NI 43-101 技术报告",
                url=pdf_url,
                kind="pdf",
            )
        )

    for key in ("quote", "trend"):
        block = evidence.get(key) or {}
        url = block.get("source_url") or ""
        label = f"{block.get('commodity', '')} 行情（{block.get('source', '')}）".strip()
        if url and url not in seen:
            seen.add(url)
            citations.append(Citation(label=label or url, url=url, kind="price"))

    return citations


def _fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:,.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _fmt_auto(value: Any, suffix: str = "") -> str:
    """金属量这类数值跨度很大（oz 是十万级、Mt 是个位级），按量级自动选小数位。"""
    if value is None or value == "":
        return "—"
    if isinstance(value, (int, float)):
        digits = 0 if abs(value) >= 1000 else 2
        return f"{value:,.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _resource_section(resource: dict[str, Any]) -> str:
    rows = resource.get("rows") or []
    if not rows:
        return "_未获取到资源量数据。_"
    lines = [
        f"**项目**：{resource.get('project') or '—'}　**矿种**：{resource.get('commodity') or '—'}"
        f"　**生效日期**：{resource.get('effective_date') or '—'}",
        "",
        "| 类别 | 矿石量 (Mt) | 品位 | 金属量 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in rows:
        grade = _fmt(row.get("grade"), 3, f" {row.get('grade_unit', '')}".rstrip())
        contained_unit = row.get("contained_unit", "")
        contained = _fmt_auto(row.get("contained_metal"), f" {contained_unit}".rstrip())
        lines.append(
            f"| {row.get('category')} | {_fmt(row.get('ore_mt'))} | {grade} | {contained} |"
        )
    pages = resource.get("source_pages") or []
    confidence = resource.get("confidence")
    lines += [
        "",
        f"_来源页：{pages or '—'}　抽取置信度：{_fmt(confidence, 2)}_",
    ]
    return "\n".join(lines)


def _price_section(quote: dict[str, Any] | None, trend: dict[str, Any] | None) -> str:
    if not quote and not trend:
        return "_未获取到价格数据。_"
    lines: list[str] = []
    if quote:
        flag = "　⚠️ **代理指标，非官方报价**" if quote.get("is_proxy") else ""
        lines.append(
            f"- **{quote.get('commodity')}**　最新价：{_fmt(quote.get('price'), 2)} "
            f"{quote.get('unit', '')}（{quote.get('date')}）{flag}"
        )
        if quote.get("note"):
            lines.append(f"  - 口径说明：{quote['note']}")
    if trend:
        flag = "　⚠️ **代理指标，非官方报价**" if trend.get("is_proxy") else ""
        change = trend.get("change_pct")
        direction = "—" if change is None else f"{change:+.2f}%"
        commodity = trend.get("commodity")
        lines.append(f"- **{commodity}**　近 {trend.get('days')} 天区间涨跌幅：{direction}{flag}")
        points = trend.get("points") or []
        if points:
            first, last = points[0]["date"], points[-1]["date"]
            lines.append(f"  - 区间：{first} → {last}，共 {len(points)} 个交易日")
    return "\n".join(lines)


def _news_section(news: list[dict[str, Any]]) -> str:
    if not news:
        return "_未获取到新闻。_"
    lines: list[str] = []
    for item in news[:10]:
        title = item.get("title") or "(无标题)"
        url = item.get("url") or ""
        source = item.get("source") or ""
        date = item.get("published") or ""
        head = f"- [{title}]({url})" if url else f"- {title}"
        meta = "　".join(part for part in (source, date) if part)
        lines.append(f"{head}　`{meta}`" if meta else head)
        summary = (item.get("summary") or "").strip()
        if summary:
            lines.append(f"  - {summary[:200]}")
    return "\n".join(lines)


def dedupe(items: list[str]) -> list[str]:
    """保序去重。同一个降级原因可能被多个工具各报一次，展示时只保留一条。"""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = (item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _degraded_section(degraded: list[str]) -> str:
    unique = dedupe(degraded)
    if not unique:
        return "本次运行未发生数据降级。"
    return "\n".join(f"- {item}" for item in unique)


def render_markdown(brief: Brief) -> str:
    """把 Brief 渲染为最终 Markdown。"""
    parts: list[str] = [
        f"# {brief.title}",
        "",
        f"> 简报对象：{brief.subject}　｜　生成时间：{brief.generated_at}",
        "> 本简报由 AI 自动生成，仅供研究参考，**不构成任何投资建议**；"
        "储量数据须由合资格人士复核。",
        "",
        "## 一、新闻摘要",
        "",
        brief.news_section or "_— _",
        "",
        "## 二、资源量（NI 43-101）",
        "",
        brief.resource_section or "_— _",
        "",
        "## 三、价格走势",
        "",
        brief.price_section or "_— _",
        "",
        "## 四、风险提示",
        "",
        brief.risk_section or "_— _",
        "",
        "## 数据降级说明",
        "",
        _degraded_section(brief.degraded),
        "",
        "## 引用来源",
        "",
    ]
    if brief.citations:
        for idx, citation in enumerate(brief.citations, 1):
            parts.append(f"{idx}. [{citation.label}]({citation.url})　`{citation.kind}`")
    else:
        parts.append("_无引用来源。_")
    parts.append("")
    return "\n".join(parts)


def fallback_brief(evidence: dict[str, Any], subject: str) -> Brief:
    """无 LLM 时的确定性渲染：模板化但不编造任何内容。"""
    resource = evidence.get("resource") or {}
    news = evidence.get("news") or []
    trend = evidence.get("trend") or {}
    quote = evidence.get("quote") or {}

    risks: list[str] = []
    if trend.get("is_proxy") or quote.get("is_proxy"):
        risks.append("价格数据为代理指标，可能与实际现货/期货价格存在显著偏离。")
    if trend.get("change_pct") is not None and abs(trend["change_pct"]) >= 10:
        window = trend.get("days")
        change = trend["change_pct"]
        risks.append(f"近 {window} 天区间波动达 {change:+.2f}%，短期价格风险偏高。")
    categories = {row.get("category") for row in resource.get("rows") or []}
    if "Inferred" in categories:
        risks.append("Inferred 资源量置信度低于 Indicated，不能直接用于储量转换。")
    if not resource.get("rows"):
        risks.append("本次未取得资源量数据，储量相关结论不成立。")
    if resource.get("warnings"):
        risks.extend(str(w) for w in resource["warnings"][:3])
    if not risks:
        risks.append("未发现显著异常，但仍需人工复核全部引用数据。")

    return Brief(
        title=f"{subject} 日报（模板渲染）",
        subject=subject,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        news_section=_news_section(news),
        resource_section=_resource_section(resource),
        price_section=_price_section(quote, trend),
        risk_section="\n".join(f"- {item}" for item in risks),
        citations=build_citations(evidence),
        degraded=dedupe(list(evidence.get("degraded") or [])),
    )


def default_title(subject: str) -> str:
    return f"{subject} 矿权日报 {today_iso()}"
