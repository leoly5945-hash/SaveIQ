"""Resolve effective feature enablement under canary / A/B (Gate 10C/10D)."""

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

AB_OVERRIDE_KEYS = {
    "router": "feature_ai_router",
    "bandit": "feature_bandit_router",
    "personalization": "feature_personalization",
    "llm_cn": "feature_chinese_llm_providers",
}


def _ab_override_bool(feature: str) -> bool | None:
    from app.services.abtest.context import get_ab_overrides

    overrides = get_ab_overrides()
    if not overrides:
        return None
    key = AB_OVERRIDE_KEYS.get(feature)
    if key is None or key not in overrides:
        return None
    return bool(overrides[key])


def is_feature_active(
    feature: str,
    *,
    settings: Settings | None = None,
    identity: str | None = None,
) -> bool:
    """Return whether a feature is active for the current (or given) identity.

    Precedence: A/B group overrides → canary cohort → global FEATURE_* flags.
    """
    cfg = settings or get_settings()
    if feature == "router":
        from app.services.safety.service import kill_switch_forces_router_fallback

        if kill_switch_forces_router_fallback(cfg):
            return False

    ab = _ab_override_bool(feature)
    if ab is not None:
        return ab
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
    """Resolve router mode with A/B overrides, then canary, then settings."""
    from app.services.abtest.context import get_ab_overrides

    cfg = settings or get_settings()
    from app.services.safety.service import kill_switch_forces_router_fallback

    if kill_switch_forces_router_fallback(cfg):
        return "disabled"
    overrides = get_ab_overrides() or {}
    if "ai_router_mode" in overrides:
        mode = str(overrides["ai_router_mode"]).lower()
        if mode in {"disabled", "mock", "live"}:
            return mode
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
