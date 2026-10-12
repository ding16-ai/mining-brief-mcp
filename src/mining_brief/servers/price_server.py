"""lme-price-mcp —— 大宗商品报价与走势。

工具签名（对外契约，勿随意改动）::

    get_price(commodity: str, date: str | None = None) -> PriceQuote
    get_trend(commodity: str, days: int = 30) -> TrendSeries

数据源策略
----------
LME / SHFE / 上海钢联的官方行情需要商业授权或登录，无法在开源 demo 中直连。
因此这里采用「可插拔 Provider + 代理指标」的做法：

1. 首选 Yahoo Finance 公开 chart 接口（无需 key），取对应期货合约收盘价；
2. 无免费直连的品种（锂、钴）使用 **代理指标**，并在返回中显式置 ``is_proxy=True``
   与 ``note``，绝不让代理数据冒充官方报价；
3. 网络不可用或离线模式时读 ``fixtures/price_*.json``，此时 ``source`` 会明确写成
   fixture，**不会**继续挂 Yahoo 的名义 —— 来源标注必须与实际取数路径一致。

更换为真实付费源只需新增一个 Provider 实现，不必改 Agent 侧代码。
"""

from __future__ import annotations

import json
import logging
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from mining_brief import cache, net
from mining_brief.config import FIXTURES_DIR, get_settings

logger = logging.getLogger(__name__)

mcp = FastMCP("lme-price")

YAHOO_CHART = "https://{host}/v8/finance/chart/{symbol}"
# Yahoo 的 chart 接口有两个可互换的入口，单个被限流时另一个常仍可用
YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
YAHOO_QUOTE = "https://finance.yahoo.com/quote/{symbol}"

# commodity -> (yahoo symbol, 计价单位, 是否代理指标, 说明)
COMMODITY_MAP: dict[str, tuple[str, str, bool, str]] = {
    "copper": ("HG=F", "USD/lb", False, "COMEX 铜期货主力合约"),
    "zinc": ("ZN=F", "USD/lb", False, "COMEX 锌期货主力合约"),
    "gold": ("GC=F", "USD/oz", False, "COMEX 黄金期货主力合约"),
    "nickel": ("NI=F", "USD/lb", False, "COMEX 镍期货主力合约"),
    "iron_ore": ("TIO=F", "USD/t", True, "SGX 铁矿石掉期，作为普氏指数的代理"),
    "lithium": ("LIT", "USD/份", True, "无免费锂盐直连报价，使用 Global X 锂矿 ETF 作代理指标"),
    "cobalt": ("COBALT", "USD/t", True, "无免费直连报价，使用内置基准值"),
}

ALIASES = {
    "锂": "lithium",
    "碳酸锂": "lithium",
    "铜": "copper",
    "锌": "zinc",
    "铁矿石": "iron_ore",
    "金": "gold",
    "黄金": "gold",
    "镍": "nickel",
    "钴": "cobalt",
    "lithium carbonate": "lithium",
    "iron ore": "iron_ore",
}


class UnknownCommodity(ValueError):
    pass


def _normalize(commodity: str) -> str:
    key = (commodity or "").strip().lower()
    key = ALIASES.get(key, key)
    if key not in COMMODITY_MAP:
        raise UnknownCommodity(
            f"不支持的品种 {commodity!r}；可选：{', '.join(sorted(COMMODITY_MAP))}"
        )
    return key


def _parse_yahoo_block(payload: dict[str, Any], symbol: str, days: int) -> list[dict[str, Any]]:
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError(f"Yahoo 未返回 {symbol} 的数据")
    block = result[0]
    stamps = block.get("timestamp") or []
    closes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    points: list[dict[str, Any]] = []
    for ts, close in zip(stamps, closes, strict=False):
        if close is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        points.append({"date": day, "price": round(float(close), 4)})
    if not points:
        raise RuntimeError(f"{symbol} 无有效收盘价")
    points.sort(key=lambda p: p["date"])
    return points[-days:]


def _yahoo_series(symbol: str, days: int) -> list[dict[str, Any]]:
    """返回 [{date, price}] 升序序列。两个 host 依次尝试，全失败才抛异常。"""
    rng = "1mo" if days <= 31 else ("3mo" if days <= 93 else "1y")
    last_error: Exception | None = None
    for host in YAHOO_HOSTS:
        try:
            payload = net.get_json(
                YAHOO_CHART.format(host=host, symbol=symbol),
                params={"range": rng, "interval": "1d"},
            )
        except Exception as exc:  # noqa: BLE001 - 换 host 重试
            last_error = exc
            continue
        try:
            return _parse_yahoo_block(payload, symbol, days)
        except Exception as exc:  # noqa: BLE001 - 换 host 重试
            last_error = exc
            continue
    raise RuntimeError(f"Yahoo 全部入口不可用：{last_error}")


def _fixture_series(commodity: str, days: int) -> list[dict[str, Any]]:
    path = FIXTURES_DIR / f"price_{commodity}.json"
    if not path.exists():
        raise FileNotFoundError(f"缺少 fixture：{path.name}")
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    points = payload.get("points") if isinstance(payload, dict) else None
    if not isinstance(points, list) or not points:
        raise ValueError(f"{path.name} 不含有效的 points 数组")
    return points[-days:]


def _series(commodity: str, days: int) -> dict[str, Any]:
    """统一取数入口。

    Returns:
        含 points / source / source_url / is_proxy / unit / note / degraded 的字典。
        ``degraded=True`` 表示数据来自内置 fixture，**不是真实行情**。
    """
    symbol, unit, is_proxy, note = COMMODITY_MAP[commodity]
    settings = get_settings()
    online_url = YAHOO_QUOTE.format(symbol=symbol)

    if settings.offline:
        return {
            "points": _fixture_series(commodity, days),
            "source": "fixture（离线模式）",
            "source_url": "",
            "is_proxy": is_proxy,
            "unit": unit,
            "note": f"{note}；数据来自内置示例 fixture，非真实行情",
            "degraded": True,
        }

    key = cache.make_key("price", commodity, days)
    state = {"degraded": False}

    def loader() -> list[dict[str, Any]]:
        try:
            return _yahoo_series(symbol, days)
        except Exception as exc:  # noqa: BLE001
            logger.warning("price: %s 在线取数失败(%s)，降级 fixture", commodity, exc)
            state["degraded"] = True
            return _fixture_series(commodity, days)

    try:
        points = cache.cached(key, loader)
    except Exception as exc:  # noqa: BLE001
        logger.warning("price: %s 全部取数失败(%s)", commodity, exc)
        state["degraded"] = True
        points = _fixture_series(commodity, days)

    if state["degraded"]:
        return {
            "points": points,
            "source": "fixture（在线源不可用）",
            "source_url": "",
            "is_proxy": is_proxy,
            "unit": unit,
            "note": f"{note}；在线取数失败，已降级为内置示例 fixture，非真实行情",
            "degraded": True,
        }

    return {
        "points": points,
        "source": f"Yahoo Finance:{symbol}",
        "source_url": online_url,
        "is_proxy": is_proxy,
        "unit": unit,
        "note": note,
        "degraded": False,
    }


@mcp.tool()
def get_price(commodity: str, date: str | None = None) -> dict[str, Any]:
    """取某个品种在指定日期（或最近交易日）的报价。

    Args:
        commodity: 品种名，支持中英文，如 lithium / 锂 / copper / 铜 / iron_ore / 铁矿石。
        date: ISO8601 日期（YYYY-MM-DD）。为空则取最新交易日。

    Returns:
        PriceQuote 字典。``is_proxy`` 为 True 时该价格为代理指标；
        ``source`` 以 ``fixture`` 开头时表示在线源不可用、已降级为示例数据。
    """
    try:
        key = _normalize(commodity)
    except UnknownCommodity as exc:
        return {"error": str(exc)}

    target = (date or "").strip()
    if target:
        try:
            _date.fromisoformat(target)
        except ValueError:
            return {"error": f"日期格式应为 YYYY-MM-DD，收到 {date!r}"}
    else:
        target = _date.today().isoformat()

    lookback = 60 if target else 30
    try:
        series = _series(key, lookback)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"取数失败：{exc}"}

    points = series["points"]
    chosen = None
    for point in reversed(points):
        if point["date"] <= target:
            chosen = point
            break
    if chosen is None:
        chosen = points[0]

    return {
        "commodity": key,
        "date": chosen["date"],
        "price": chosen["price"],
        "unit": series["unit"],
        "currency": "USD",
        "source": series["source"],
        "source_url": series["source_url"],
        "is_proxy": series["is_proxy"],
        "note": series["note"],
        "degraded": series["degraded"],
    }


@mcp.tool()
def get_trend(commodity: str, days: int = 30) -> dict[str, Any]:
    """取某品种最近 N 天的价格走势。

    Args:
        commodity: 品种名，支持中英文。
        days: 回溯天数，默认 30，上限 365。

    Returns:
        TrendSeries 字典，含 points、区间涨跌幅 ``change_pct``、代理指标标记 ``is_proxy``
        与降级标记 ``degraded``。
    """
    try:
        key = _normalize(commodity)
    except UnknownCommodity as exc:
        return {"error": str(exc)}

    days = max(2, min(int(days), 365))
    try:
        series = _series(key, days)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"取数失败：{exc}"}

    points = series["points"]
    change_pct: float | None = None
    if len(points) >= 2 and points[0]["price"]:
        change_pct = round((points[-1]["price"] - points[0]["price"]) / points[0]["price"] * 100, 2)

    return {
        "commodity": key,
        "days": days,
        "points": points,
        "unit": series["unit"],
        "source": series["source"],
        "source_url": series["source_url"],
        "is_proxy": series["is_proxy"],
        "change_pct": change_pct,
        "note": series["note"],
        "degraded": series["degraded"],
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
