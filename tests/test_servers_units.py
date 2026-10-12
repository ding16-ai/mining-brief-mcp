"""三个 MCP server 内部纯函数的单元测试。

这些函数不碰网络、不起子进程，直接 import 调用即可，
用来补齐 ``test_servers_offline.py`` 走 stdio 时覆盖不到的边界分支。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mining_brief.servers import news_server, pdf_server, price_server
from mining_brief.servers.price_server import UnknownCommodity


class TestNewsHelpers:
    def test_strip_html_removes_tags(self) -> None:
        assert news_server._strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_to_iso_parses_struct_time(self) -> None:
        class Entry:
            # feedparser 的 published_parsed 是 9 元组 struct_time。
            published_parsed = (2026, 10, 12, 8, 30, 0, 0, 285, 0)

        assert news_server._to_iso(Entry()) == "2026-10-12"

    def test_to_iso_falls_back_to_raw_string(self) -> None:
        class Entry:
            published = "2026-10-12T08:30:00Z"

        assert news_server._to_iso(Entry()) == "2026-10-12"

    def test_to_iso_returns_empty_when_nothing_available(self) -> None:
        class Entry:
            pass

        assert news_server._to_iso(Entry()) == ""

    def test_fixture_returns_all_when_keyword_misses(self) -> None:
        items = news_server._load_fixture("zzz-nonexistent-token", 7)
        assert items, "关键词没命中时也应返回全部 fixture，避免产出空简报"

    def test_fixture_items_have_required_keys(self) -> None:
        items = news_server._load_fixture("Pilbara", 7)
        assert items
        assert all({"title", "url", "source"} <= set(item) for item in items)


class TestPdfPageSelection:
    def test_scores_and_sorts_candidate_pages(self) -> None:
        texts = [
            "cover page",
            "mineral resource estimate indicated inferred tonnes grade",
            "indicated inferred",
            "no hits here",
            "mineral resource tonnes grade indicated",
        ]
        assert pdf_server._candidate_pages(texts) == [2, 3, 5]

    def test_ignores_pages_with_weak_hits(self) -> None:
        texts = ["indicated", "nothing relevant", "inferred and indicated"]
        assert pdf_server._candidate_pages(texts) == [3]


class TestPdfRowNormalization:
    def test_converts_unconverted_tonnes(self) -> None:
        rows, warnings = pdf_server._normalize_rows(
            [{"category": "Indicated", "ore_mt": 12_300_000.0, "grade": 1.2, "grade_unit": "%"}]
        )
        assert rows[0].ore_mt == 12.3
        assert any("疑似未换算单位" in warning for warning in warnings)

    def test_drops_row_with_invalid_category(self) -> None:
        rows, warnings = pdf_server._normalize_rows([{"category": "Bogus", "ore_mt": 1.0}])
        assert rows == []
        assert any("丢弃非法行" in warning for warning in warnings)

    def test_warns_on_unexpected_grade_unit(self) -> None:
        rows, warnings = pdf_server._normalize_rows(
            [{"category": "Indicated", "ore_mt": 1.0, "grade": 0.5, "grade_unit": "ppm"}]
        )
        assert rows
        assert any("品位单位异常" in warning for warning in warnings)


class TestPdfFixtureSafety:
    def test_fixture_scheme_returns_bundled_sample(self) -> None:
        table = pdf_server.extract_resources("fixture://resources_pilbara")
        assert table["rows"], "fixture:// 应返回内置示例数据"
        assert any("fixture://" in warning for warning in table["warnings"])

    def test_blank_url_returns_error(self) -> None:
        assert "error" in pdf_server.extract_resources("   ")

    def test_missing_fixture_file_yields_empty_table(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(pdf_server, "FIXTURES_DIR", tmp_path)
        table = pdf_server._load_fixture("gold")
        assert table["rows"] == []
        assert table["commodity"] == "gold"
        assert table["warnings"], "fixture 缺失也必须留下可追溯的说明"

    def test_corrupt_fixture_file_yields_empty_table(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "resources_pilbara.json").write_text("{ not json", encoding="utf-8")
        monkeypatch.setattr(pdf_server, "FIXTURES_DIR", tmp_path)
        table = pdf_server._load_fixture()
        assert table["rows"] == []
        assert any("读取失败" in warning for warning in table["warnings"])


class TestPriceHelpers:
    def test_chinese_aliases_normalize(self) -> None:
        assert price_server._normalize("锂") == "lithium"
        assert price_server._normalize("碳酸锂") == "lithium"
        assert price_server._normalize("铁矿石") == "iron_ore"

    def test_unknown_commodity_raises(self) -> None:
        with pytest.raises(UnknownCommodity):
            price_server._normalize("unobtainium")

    def test_bad_date_returns_error_not_exception(self) -> None:
        assert "error" in price_server.get_price("lithium", "2026/10/09")

    def test_trend_clamps_days_to_upper_bound(self) -> None:
        assert price_server.get_trend("lithium", 9999)["days"] == 365

    def test_offline_trend_does_not_claim_upstream_source(self) -> None:
        trend = price_server.get_trend("copper", 10)
        assert trend["source"].startswith("fixture")
        assert trend["degraded"] is True
        assert trend["source_url"] == "", "降级后不得继续挂 Yahoo 的名义"

    def test_fixture_series_is_sorted_ascending(self) -> None:
        points = price_server._fixture_series("gold", 10)
        dates = [point["date"] for point in points]
        assert dates == sorted(dates)

    def test_parse_yahoo_block_skips_nulls(self) -> None:
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_760_000_000, 1_760_086_400],
                        "indicators": {"quote": [{"close": [10.0, None]}]},
                    }
                ]
            }
        }
        points = price_server._parse_yahoo_block(payload, "TEST", 30)
        assert len(points) == 1
        assert points[0]["price"] == 10.0

    def test_parse_yahoo_block_raises_without_data(self) -> None:
        with pytest.raises(RuntimeError):
            price_server._parse_yahoo_block({"chart": {"result": []}}, "TEST", 30)
