"""磁盘缓存。目的只有一个：让重复 demo 不重复打网络，同时让离线演示可用。"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from mining_brief.config import get_settings

T = TypeVar("T")


def make_key(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _path_for(key: str) -> Path:
    settings = get_settings()
    return settings.cache_dir / f"{key}.json"


def read(key: str, ttl: int | None = None) -> Any | None:
    """读缓存；过期或不存在返回 None。"""
    settings = get_settings()
    path = _path_for(key)
    if not path.exists():
        return None
    ttl = settings.cache_ttl if ttl is None else ttl
    age = time.time() - path.stat().st_mtime
    if ttl >= 0 and age > ttl:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write(key: str, payload: Any) -> None:
    settings = get_settings()
    settings.ensure_dirs()
    path = _path_for(key)
    # 缓存写失败不应影响主流程
    with contextlib.suppress(OSError):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cached(key: str, loader: Callable[[], T], ttl: int | None = None) -> T:
    """带缓存的取值：命中直接返回，未命中调用 loader 并落盘。

    loader 抛异常时不写缓存，异常向上抛，由调用方决定降级策略。
    """
    hit = read(key, ttl)
    if hit is not None:
        return hit  # type: ignore[return-value]
    value = loader()
    if value is not None:
        write(key, value)
    return value
