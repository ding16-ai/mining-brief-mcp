"""集中式配置。所有可调参数只在这里读取环境变量，其余模块一律从 Settings 取。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# src/mining_brief/config.py -> src/mining_brief -> src -> <project root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


@dataclass(frozen=True)
class Settings:
    """运行时配置快照。"""

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    offline: bool
    cache_dir: Path
    cache_ttl: int
    http_timeout: float
    user_agent: str
    default_pdf_url: str

    @property
    def llm_enabled(self) -> bool:
        """没配 key 时自动降级为「纯规则模式」，demo 依然能跑。"""
        return bool(self.llm_api_key and not self.llm_api_key.startswith("sk-xxx"))

    def ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings(
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat").strip(),
        offline=_env_bool("MINING_BRIEF_OFFLINE", False),
        cache_dir=_env_path("MINING_BRIEF_CACHE_DIR", PROJECT_ROOT / "data" / "cache"),
        cache_ttl=int(os.getenv("MINING_BRIEF_CACHE_TTL", "3600")),
        http_timeout=float(os.getenv("MINING_BRIEF_HTTP_TIMEOUT", "20")),
        user_agent=os.getenv(
            "MINING_BRIEF_USER_AGENT",
            "mining-brief-mcp/0.1 (+https://github.com/your-name/mining-brief-mcp)",
        ),
        default_pdf_url=os.getenv("MINING_BRIEF_DEFAULT_PDF", "").strip(),
    )
    settings.ensure_dirs()
    return settings


def reload_settings() -> Settings:
    """测试用：清缓存后重新读取环境变量。"""
    get_settings.cache_clear()
    return get_settings()
