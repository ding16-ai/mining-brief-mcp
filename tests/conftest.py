"""测试公共夹具。

所有测试默认跑在**离线模式**：不联网、不调模型，只读包内 fixture。
这样 CI 结果稳定，也不依赖外部数据源的可用性。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from mining_brief.config import reload_settings


@pytest.fixture(autouse=True)
def offline_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MINING_BRIEF_OFFLINE", "true")
    monkeypatch.setenv("MINING_BRIEF_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MINING_BRIEF_DEFAULT_PDF", "")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    reload_settings()
    yield
    reload_settings()
