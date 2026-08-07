"""Resolve effective feature enablement under canary (Gate 10C)."""

from __future__ import annotations

from app.core.settings import Settings, get_settings
from app.services.canary.context import get_canary_identity
from app.services.canary.service import build_canary_service

FEATURE_TO_SETTING = {
    "router": "feature_ai_router",
    "bandit": "feature_bandit_router",
    "personalization": "feature_personalization",
    "llm_cn": "feature_chinese_llm_providers",
}


def is_feature_active(
    feature: str,
    *,
    settings: Settings | None = None,
    identity: str | None = None,
) -> bool:
    """Return whether a feature is active for the current (or given) identity.

    When canary is disabled: use global FEATURE_* flags.
    When canary is enabled: only the canary cohort for listed features gets them
    (global FEATURE_* may still force-on for everyone).
    """
    cfg = settings or get_settings()
    global_on = bool(getattr(cfg, FEATURE_TO_SETTING.get(feature, ""), False))
    service = build_canary_service(cfg)
    config = service.get_config()
    if not config.enabled:
        return global_on

    # Global force-on still wins (full rollout without waiting for 100% canary).
    if global_on:
        return True

    subject = identity if identity is not None else get_canary_identity()
    return service.is_canary(subject, feature)


def effective_ai_router_mode(settings: Settings | None = None) -> str:
    """When canary enables router but mode is disabled, prefer safe mock mode."""
    cfg = settings or get_settings()
    if is_feature_active("router", settings=cfg):
        if cfg.ai_router_mode == "disabled":
            return "mock"
        return cfg.ai_router_mode
    return cfg.ai_router_mode


def effective_bandit_mode(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    if is_feature_active("bandit", settings=cfg):
        if cfg.bandit_router_mode == "disabled":
            return "logging"
        return cfg.bandit_router_mode
    return cfg.bandit_router_mode
