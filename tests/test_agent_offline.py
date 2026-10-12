"""Agent 编排的离线测试（不调用任何模型）。"""

from __future__ import annotations

import pytest

from mining_brief.agent.client import extract_subject, run_agent


def test_extract_subject_chinese() -> None:
    assert extract_subject("生成一份关于 Pilbara 锂矿的今日简报") == "Pilbara 锂矿"


def test_extract_subject_english() -> None:
    assert extract_subject("brief me about Pilbara lithium") == "Pilbara lithium"


def test_extract_subject_default() -> None:
    assert extract_subject("来一份日报") == "Pilbara 锂矿"


@pytest.mark.asyncio
async def test_run_agent_offline_produces_cited_markdown() -> None:
    brief, markdown = await run_agent("生成一份关于 Pilbara 锂矿的今日简报", use_llm=False)
    assert brief.citations, "简报必须带引用来源"
    assert "## 引用来源" in markdown
    assert "不构成任何投资建议" in markdown
    assert "## 数据降级说明" in markdown


@pytest.mark.asyncio
async def test_run_agent_offline_marks_missing_pdf_as_degraded() -> None:
    brief, _ = await run_agent("生成一份关于 Pilbara 锂矿的今日简报", use_llm=False)
    assert any("MINING_BRIEF_DEFAULT_PDF" in item for item in brief.degraded), (
        "未配置 PDF 时应显式标注降级，而不是静默跳过"
    )
