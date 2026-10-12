"""数据模型与简报渲染的单元测试。"""

from __future__ import annotations

from mining_brief.agent.brief import (
    build_citations,
    fallback_brief,
    render_markdown,
)
from mining_brief.models import ResourceRow, ResourceTable, TrendPoint, TrendSeries


def test_resource_table_total_ore():
    table = ResourceTable(
        project="Demo",
        rows=[
            ResourceRow(category="Indicated", ore_mt=100.0, grade=1.2, grade_unit="%"),
            ResourceRow(category="Inferred", ore_mt=50.0, grade=1.0, grade_unit="%"),
        ],
    )
    assert table.total_ore_mt == 150.0


def test_resource_row_rejects_bad_category():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResourceRow(category="NotACategory", ore_mt=1.0)  # type: ignore[arg-type]


def test_build_citations_dedupes_and_classifies():
    evidence = {
        "news": [
            {"title": "a", "url": "https://example.com/a", "source": "mining.com"},
            {"title": "b", "url": "https://example.com/a", "source": "mining.com"},
        ],
        "resource": {"project": "Demo", "source_url": "https://example.com/report.pdf"},
        "trend": {
            "source": "Yahoo Finance:LIT",
            "source_url": "https://finance.yahoo.com/quote/LIT",
            "commodity": "lithium",
        },
    }
    citations = build_citations(evidence)
    urls = [c.url for c in citations]
    assert len(urls) == len(set(urls)), "引用必须去重"
    assert {c.kind for c in citations} == {"news", "pdf", "price"}


def test_fallback_brief_flags_proxy_price():
    evidence = {
        "subject": "Pilbara 锂矿",
        "news": [],
        "articles": [],
        "resource": {"rows": [], "warnings": []},
        "quote": {
            "commodity": "lithium",
            "is_proxy": True,
            "price": 62.0,
            "unit": "USD/份",
            "date": "2026-01-01",
        },
        "trend": TrendSeries(
            commodity="lithium",
            days=30,
            is_proxy=True,
            change_pct=-14.5,
            points=[TrendPoint(date="2026-01-01", price=62.0)],
        ).model_dump(),
        "degraded": [],
    }
    brief = fallback_brief(evidence, "Pilbara 锂矿")
    markdown = render_markdown(brief)
    assert "代理指标" in markdown
    assert "不构成任何投资建议" in markdown
    assert "引用来源" in markdown


def test_fallback_brief_handles_empty_evidence():
    evidence = {
        "subject": "X 矿",
        "news": [],
        "articles": [],
        "resource": {},
        "quote": {},
        "trend": {},
        "degraded": ["新闻源不可用"],
    }
    markdown = render_markdown(fallback_brief(evidence, "X 矿"))
    assert "未获取到资源量数据" in markdown
    assert "新闻源不可用" in markdown
