"""生成离线 fixture（可复现）。

    python scripts/make_fixtures.py

价格 fixture 是**合成序列**，只用于离线演示链路是否打通，**不是真实行情**。
真实行情请在联网模式下由 lme-price-mcp 从公开接口获取。
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "src" / "mining_brief" / "fixtures"

# commodity -> (起始价, 日波动率, 单位, 说明)
SPECS: dict[str, tuple[float, float, str, str]] = {
    "lithium": (62.0, 0.018, "USD/份", "Global X 锂矿 ETF (LIT) 代理指标"),
    "copper": (4.35, 0.011, "USD/lb", "COMEX 铜期货主力合约"),
    "iron_ore": (102.0, 0.013, "USD/t", "SGX 铁矿石掉期代理"),
    "zinc": (1.32, 0.012, "USD/lb", "COMEX 锌期货主力合约"),
    "gold": (2650.0, 0.008, "USD/oz", "COMEX 黄金期货主力合约"),
    "nickel": (7.10, 0.016, "USD/lb", "COMEX 镍期货主力合约"),
    "cobalt": (33500.0, 0.010, "USD/t", "钴现货基准价代理"),
}

DAYS = 60


def build_series(commodity: str) -> dict[str, Any]:
    start_price, vol, unit, note = SPECS[commodity]
    rng = random.Random(f"mining-brief-{commodity}")
    points: list[dict[str, Any]] = []
    price = start_price
    today = date.today()
    for offset in range(DAYS, 0, -1):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:  # 跳过周末，模拟交易日
            continue
        drift = math.sin(offset / 7.0) * vol * 0.6
        price = max(0.01, price * (1 + rng.gauss(drift, vol)))
        points.append({"date": day.isoformat(), "price": round(price, 4)})
    return {
        "fixture_note": "合成数据，仅用于离线演示，不是真实行情",
        "commodity": commodity,
        "unit": unit,
        "note": note,
        "points": points,
    }


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for commodity in SPECS:
        target = FIXTURES / f"price_{commodity}.json"
        target.write_text(
            json.dumps(build_series(commodity), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已生成 {target.relative_to(FIXTURES.parents[2])}")


if __name__ == "__main__":
    main()
