"""Gate 10D config accessors (canonical values live on Settings)."""

from __future__ import annotations

from app.core.settings import Settings, get_settings

# Prompt-facing defaults (overridden by env / Settings).
FEATURE_ABTEST_ENABLED: bool = False
ABTEST_CONFIG_PATH: str = "config/abtest.yaml"
ABTEST_REDIS_TTL: int = 2592000


def feature_abtest_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(cfg.feature_abtest_enabled)


def abtest_config_path(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    return cfg.abtest_config_path or ABTEST_CONFIG_PATH


def abtest_redis_ttl(settings: Settings | None = None) -> int:
    cfg = settings or get_settings()
    return int(cfg.abtest_redis_ttl)
