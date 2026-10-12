"""mining-news-mcp —— 矿业新闻检索与正文抓取。

工具签名（对外契约，勿随意改动）::

    search(query: str, days: int = 7) -> list[Article]
    fetch_article(url: str) -> ArticleDetail

数据源策略：优先 Google News RSS（覆盖面广、无需 key），失败则退回 mining.com 官方
RSS；两者都不可用或处于离线模式时，读 ``fixtures/news_*.json`` 保证 demo 不中断。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any

import feedparser
from mcp.server.fastmcp import FastMCP

from mining_brief import cache, net
from mining_brief.config import FIXTURES_DIR, get_settings

logger = logging.getLogger(__name__)

mcp = FastMCP("mining-news")

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
MINING_COM_RSS = "https://www.mining.com/feed/"
# 备用源：部分站点会按 UA/地域返回 403，多备几个能显著提高在线成功率
FALLBACK_FEEDS = (
    ("https://www.australianmining.com.au/feed/", "australianmining.com.au"),
    ("https://www.mining-technology.com/feed/", "mining-technology.com"),
)
MAX_ARTICLE_CHARS = 6000

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_RE = re.compile(r"\n{3,}")


def _strip_html(raw: str) -> str:
    text = unescape(_TAG_RE.sub(" ", raw or ""))
    text = _WS_RE.sub(" ", text)
    return _BLANK_RE.sub("\n\n", text).strip()


def _to_iso(entry: Any) -> str:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                # 显式解包前 6 个字段再传 tzinfo。feedparser 给的是 9 元组
                # struct_time，用 *parsed[:6] 展开会让位置参数与 tzinfo 撞车。
                year, month, day, hour, minute, second = parsed[:6]
                stamp = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
                return stamp.date().isoformat()
            except (TypeError, ValueError):
                continue
    raw = getattr(entry, "published", "") or ""
    return raw[:10] if len(raw) >= 10 else ""


def _load_fixture(query: str, days: int) -> list[dict[str, Any]]:
    """离线兜底：读取包内 fixture，按 query 关键字做粗筛。"""
    import json

    path = FIXTURES_DIR / "news_pilbara.json"
    if not path.exists():
        return []
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    # fixture 允许写成 {"articles": [...]} 或裸数组两种形状，统一成列表并剔除非对象项。
    raw = payload.get("articles", []) if isinstance(payload, dict) else payload
    items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    if not items:
        return []

    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    if not tokens:
        return items[:20]
    hits = [
        article
        for article in items
        if any(
            token in (str(article.get("title", "")) + str(article.get("summary", ""))).lower()
            for token in tokens
        )
    ]
    # 离线 fixture 只有少量条目，过度筛选会让 demo 变成空简报；
    # 命中不足 2 条时直接返回全部，宁可宽泛也不要空。
    return hits if len(hits) >= 2 else items[:20]


def _fetch_from_rss(url: str) -> list[dict[str, Any]]:
    raw = net.get_text(url)
    parsed = feedparser.parse(raw)
    items: list[dict[str, Any]] = []
    for entry in parsed.entries:
        source = ""
        if getattr(entry, "source", None) is not None:
            source = getattr(entry.source, "title", "") or ""
        items.append(
            {
                "title": _strip_html(getattr(entry, "title", "")),
                "url": getattr(entry, "link", ""),
                "source": source or "Google News",
                "published": _to_iso(entry),
                "summary": _strip_html(getattr(entry, "summary", ""))[:600],
            }
        )
    return items


@mcp.tool()
def search(query: str, days: int = 7) -> list[dict[str, Any]]:
    """按关键词检索最近 N 天的矿业新闻。

    Args:
        query: 检索关键词，例如 "Pilbara lithium"。
        days: 回溯天数，默认 7。

    Returns:
        新闻列表，每条含 title / url / source / published / summary。
    """
    settings = get_settings()
    days = max(1, min(int(days), 90))
    key = cache.make_key("news", query.lower().strip(), days)

    def loader() -> list[dict[str, Any]]:
        attempts = [
            (GOOGLE_NEWS_RSS.format(query=query.replace(" ", "+")), "Google News"),
            (MINING_COM_RSS, "mining.com"),
            *FALLBACK_FEEDS,
        ]
        collected: list[dict[str, Any]] = []
        errors: list[str] = []
        for url, label in attempts:
            try:
                collected = _fetch_from_rss(url)
                logger.info("news: %s 返回 %d 条", label, len(collected))
                if collected:
                    break
            except Exception as exc:  # noqa: BLE001 - 网络层任何异常都应降级
                errors.append(f"{label}: {exc}")
                logger.warning("news: %s 抓取失败: %s", label, exc)

        if not collected:
            logger.warning("news: 全部数据源失败，降级 fixture（%s）", "; ".join(errors))
            return _load_fixture(query, days)

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        fresh = [a for a in collected if not a["published"] or a["published"] >= cutoff]
        return fresh or collected

    if settings.offline:
        return _load_fixture(query, days)

    try:
        return cache.cached(key, loader)
    except Exception as exc:  # noqa: BLE001
        logger.warning("news: 缓存层异常，降级 fixture: %s", exc)
        return _load_fixture(query, days)


@mcp.tool()
def fetch_article(url: str) -> dict[str, Any]:
    """抓取单篇文章正文（纯文本，按 6000 字符截断）。

    Args:
        url: 文章 URL。

    Returns:
        含 title / url / source / published / summary / text / truncated 的字典。
    """
    if not url:
        return {"error": "url 不能为空"}

    key = cache.make_key("article", url)

    def loader() -> dict[str, Any]:
        html = net.get_text(url)
        text = _strip_html(html)
        truncated = len(text) > MAX_ARTICLE_CHARS
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = _strip_html(title_match.group(1)) if title_match else ""
        host = re.sub(r"^https?://", "", url).split("/")[0]
        return {
            "title": title,
            "url": url,
            "source": host,
            "published": "",
            "summary": text[:400],
            "text": text[:MAX_ARTICLE_CHARS],
            "truncated": truncated,
        }

    try:
        return cache.cached(key, loader)
    except Exception as exc:  # noqa: BLE001
        logger.warning("news: 正文抓取失败 %s: %s", url, exc)
        return {
            "title": "",
            "url": url,
            "source": "",
            "published": "",
            "summary": "",
            "text": "",
            "truncated": False,
            "error": f"抓取失败：{exc}",
        }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
