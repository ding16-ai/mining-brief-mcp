"""核心模块的单元测试：配置、缓存、HTTP 收口、LLM 解析、简报渲染。

与 ``test_servers_offline.py``（走真实 stdio 子进程的集成测试）互补：
这里直接 import 内部函数，覆盖子进程模式下统计不到的边界分支。
"""

from __future__ import annotations

import json
import os
import time

import pytest

from mining_brief import cache, net
from mining_brief.agent.brief import (
    _fmt_auto,
    _news_section,
    _price_section,
    _resource_section,
    dedupe,
    default_title,
    evidence_to_prompt_block,
)
from mining_brief.agent.client import (
    MCPToolkit,
    _empty_evidence,
    _note_price_degradation,
    _route_result,
)
from mining_brief.cli import build_parser
from mining_brief.config import get_settings, reload_settings
from mining_brief.llm import LLM, LLMUnavailable, _extract_json
from mining_brief.models import today_iso


class TestSettings:
    def test_offline_flag_accepts_truthy_strings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINING_BRIEF_OFFLINE", "yes")
        assert reload_settings().offline is True
        monkeypatch.setenv("MINING_BRIEF_OFFLINE", "0")
        assert reload_settings().offline is False

    def test_placeholder_key_is_not_treated_as_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_API_KEY", "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        assert reload_settings().llm_enabled is False, "占位 key 不能让项目以为模型可用"
        monkeypatch.setenv("LLM_API_KEY", "sk-real-looking-key")
        assert reload_settings().llm_enabled is True


class TestCache:
    def test_roundtrip(self) -> None:
        key = cache.make_key("unit", "roundtrip")
        assert cache.read(key) is None
        cache.write(key, {"a": 1})
        assert cache.read(key) == {"a": 1}

    def test_expires_after_ttl(self) -> None:
        key = cache.make_key("unit", "expire")
        cache.write(key, {"k": "v"})
        path = get_settings().cache_dir / f"{key}.json"
        stale = time.time() - 10_000
        os.utime(path, (stale, stale))
        assert cache.read(key, ttl=3600) is None

    def test_negative_ttl_never_expires(self) -> None:
        key = cache.make_key("unit", "no-expire")
        cache.write(key, {"k": "v"})
        assert cache.read(key, ttl=-1) == {"k": "v"}

    def test_corrupt_file_is_treated_as_miss(self) -> None:
        key = cache.make_key("unit", "corrupt")
        (get_settings().cache_dir / f"{key}.json").write_text("{ not json", encoding="utf-8")
        assert cache.read(key) is None

    def test_cached_calls_loader_only_once(self) -> None:
        calls: list[int] = []

        def loader() -> list[int]:
            calls.append(1)
            return [1, 2]

        key = cache.make_key("unit", "loader")
        assert cache.cached(key, loader) == [1, 2]
        assert cache.cached(key, loader) == [1, 2]
        assert len(calls) == 1, "第二次应命中缓存，不应再调用 loader"


class TestNetGuard:
    def test_offline_mode_blocks_every_request(self) -> None:
        with pytest.raises(net.OfflineMode):
            net.get_text("https://example.com")
        with pytest.raises(net.OfflineMode):
            net.get_bytes("https://example.com")
        with pytest.raises(net.OfflineMode):
            net.get_json("https://example.com")


class TestExtractJson:
    def test_plain_object(self) -> None:
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_code_block(self) -> None:
        assert _extract_json('```json\n{"a": 2}\n```') == {"a": 2}

    def test_object_wrapped_in_prose(self) -> None:
        assert _extract_json('好的，结果如下：{"a": 3} 以上。') == {"a": 3}

    def test_non_object_payload_is_rejected(self) -> None:
        with pytest.raises(LLMUnavailable):
            _extract_json("[1, 2, 3]")

    def test_garbage_raises(self) -> None:
        with pytest.raises(LLMUnavailable):
            _extract_json("完全不是 JSON")


class TestLLMGuard:
    def test_client_raises_without_api_key(self) -> None:
        llm = LLM()
        assert llm.available is False
        with pytest.raises(LLMUnavailable):
            _ = llm.client


class TestBriefRendering:
    def test_dedupe_keeps_order_and_drops_blanks(self) -> None:
        assert dedupe(["b", "a", "b", "", "  ", "a", "c"]) == ["b", "a", "c"]

    def test_fmt_auto_keeps_precision_for_small_values(self) -> None:
        assert _fmt_auto(5.71, " Mt Li2O") == "5.71 Mt Li2O"
        assert _fmt_auto(573000, " oz") == "573,000 oz"
        assert _fmt_auto(None) == "—"

    def test_news_section_has_placeholder_when_empty(self) -> None:
        assert "未获取到新闻" in _news_section([])

    def test_price_section_flags_proxy_and_change(self) -> None:
        quote = {
            "commodity": "lithium",
            "price": 58.688,
            "unit": "USD/份",
            "date": "2026-10-09",
            "is_proxy": True,
            "note": "代理说明",
        }
        trend = {
            "commodity": "lithium",
            "days": 30,
            "change_pct": -7.37,
            "is_proxy": True,
            "points": [
                {"date": "2026-08-31", "price": 63.0},
                {"date": "2026-10-09", "price": 58.688},
            ],
        }
        text = _price_section(quote, trend)
        assert "代理指标" in text
        assert "-7.37%" in text
        assert "58.69" in text

    def test_price_section_handles_no_data(self) -> None:
        assert "未获取到价格数据" in _price_section(None, None)

    def test_resource_section_renders_table_row(self) -> None:
        text = _resource_section(
            {
                "project": "P",
                "commodity": "lithium",
                "effective_date": "2025-06-11",
                "rows": [
                    {
                        "category": "Total",
                        "ore_mt": 446.0,
                        "grade": 1.28,
                        "grade_unit": "%",
                        "contained_metal": 5.71,
                        "contained_unit": "Mt Li2O",
                    }
                ],
                "source_pages": [12],
                "confidence": 0.6,
            }
        )
        assert "| Total | 446.00 |" in text
        assert "5.71 Mt Li2O" in text

    def test_evidence_block_is_valid_json(self) -> None:
        block = evidence_to_prompt_block({"news": [], "resource": {}})
        assert json.loads(block) == {"news": [], "resource": {}}

    def test_default_title_contains_subject_and_date(self) -> None:
        title = default_title("Pilbara 锂矿")
        assert "Pilbara 锂矿" in title
        assert today_iso() in title


class TestEvidenceRouting:
    def test_tool_error_is_recorded_as_degraded(self) -> None:
        evidence = _empty_evidence("X")
        _route_result(evidence, "search", {"query": "x"}, {"error": "boom"})
        assert evidence["news"] == []
        assert any("失败：boom" in item for item in evidence["degraded"])

    def test_search_list_lands_in_news(self) -> None:
        evidence = _empty_evidence("X")
        _route_result(evidence, "search", {"query": "x"}, [{"title": "t"}])
        assert evidence["news"] == [{"title": "t"}]

    def test_proxy_and_fixture_degradation_both_recorded(self) -> None:
        evidence = _empty_evidence("X")
        _note_price_degradation(
            evidence,
            {
                "commodity": "lithium",
                "is_proxy": True,
                "note": "代理说明",
                "source": "fixture（离线模式）",
            },
        )
        joined = " ".join(evidence["degraded"])
        assert "代理指标" in joined
        assert "降级为内置示例 fixture" in joined

    @pytest.mark.asyncio
    async def test_toolkit_rejects_unknown_tool(self) -> None:
        with pytest.raises(KeyError):
            await MCPToolkit().call("nope", {})


class TestCliParser:
    def test_brief_defaults(self) -> None:
        args = build_parser().parse_args(["brief"])
        assert args.request == "生成一份关于 Pilbara 锂矿的今日简报"
        assert args.no_llm is False

    def test_serve_rejects_unknown_server(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["serve", "nope"])
