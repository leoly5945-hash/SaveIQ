#!/usr/bin/env python3
"""Validate Render staging or production Blueprints before applying them."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only outside the dev environment
    yaml = None


PLACEHOLDER_PATTERN = re.compile(r"<[A-Z0-9_]+>")
DIGEST_PATTERN = re.compile(r"@sha256:[a-fA-F0-9]{64}$")

PROFILES: dict[str, dict[str, Any]] = {
    "staging": {
        "services": {
            "dealhunter-staging-api": "web",
            "dealhunter-staging-web": "web",
            "dealhunter-staging-redis": "keyvalue",
        },
        "databases": {"dealhunter-staging-postgres"},
        "api": "dealhunter-staging-api",
        "web": "dealhunter-staging-web",
        "redis": "dealhunter-staging-redis",
        "postgres": "dealhunter-staging-postgres",
        "environment": "staging",
        "paid_plans": False,
        "rate_limit_required": False,
        "ok": "staging_provisioning_validation=ok",
        "ok_template": "staging_provisioning_template_validation=ok",
    },
    "production": {
        "services": {
            "dealhunter-production-api": "web",
            "dealhunter-production-web": "web",
            "dealhunter-production-redis": "keyvalue",
        },
        "databases": {"dealhunter-production-postgres"},
        "api": "dealhunter-production-api",
        "web": "dealhunter-production-web",
        "redis": "dealhunter-production-redis",
        "postgres": "dealhunter-production-postgres",
        "environment": "production",
        "paid_plans": True,
        "rate_limit_required": True,
        "ok": "production_provisioning_validation=ok",
        "ok_template": "production_provisioning_template_validation=ok",
    },
}


def fail(message: str, *, profile: str) -> None:
    prefix = (
        "production_provisioning_validation=error"
        if profile == "production"
        else "staging_provisioning_validation=error"
    )
    print(f"{prefix}: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_blueprint(path: Path, *, profile: str) -> tuple[str, dict[str, Any]]:
    if yaml is None:
        fail(
            "PyYAML is required. Run this with the backend virtual environment.",
            profile=profile,
        )

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        fail("blueprint must parse to a YAML object", profile=profile)
    return raw, data


def env_map(service: dict[str, Any], *, profile: str) -> dict[str, dict[str, Any]]:
    env_vars = service.get("envVars", [])
    if not isinstance(env_vars, list):
        fail(f"{service.get('name')} envVars must be a list", profile=profile)

    mapped: dict[str, dict[str, Any]] = {}
    for item in env_vars:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            fail(f"{service.get('name')} has an invalid env var entry", profile=profile)
        mapped[item["key"]] = item
    return mapped


def service_by_name(data: dict[str, Any], *, profile: str) -> dict[str, dict[str, Any]]:
    services = data.get("services")
    if not isinstance(services, list):
        fail("services must be a list", profile=profile)

    mapped: dict[str, dict[str, Any]] = {}
    for service in services:
        if not isinstance(service, dict):
            fail("each service must be an object", profile=profile)
        name = service.get("name")
        if not isinstance(name, str):
            fail("each service must have a name", profile=profile)
        mapped[name] = service
    return mapped


def validate_services(
    services: dict[str, dict[str, Any]],
    *,
    profile: str,
    allow_placeholders: bool,
) -> None:
    expected = PROFILES[profile]["services"]
    missing = set(expected) - set(services)
    if missing:
        fail(f"missing services: {', '.join(sorted(missing))}", profile=profile)

    for name, expected_type in expected.items():
        service = services[name]
        if service.get("type") != expected_type:
            fail(f"{name} must be type {expected_type}", profile=profile)

    for name in (PROFILES[profile]["api"], PROFILES[profile]["web"]):
        service = services[name]
        if service.get("runtime") != "image":
            fail(f"{name} must use runtime: image", profile=profile)

        if PROFILES[profile]["paid_plans"]:
            plan = service.get("plan")
            if plan in {None, "free"}:
                fail(f"{name} must use a paid plan (not free)", profile=profile)
            if service.get("numInstances") is None:
                fail(f"{name} must set numInstances", profile=profile)
            if service.get("autoDeployTrigger") != "off":
                fail(f"{name} must set autoDeployTrigger: off", profile=profile)

        image = service.get("image")
        if not isinstance(image, dict) or not isinstance(image.get("url"), str):
            fail(f"{name} must define image.url", profile=profile)

        creds = image.get("creds")
        registry_creds = (
            creds.get("fromRegistryCreds") if isinstance(creds, dict) else None
        )
        if (
            not isinstance(registry_creds, dict)
            or registry_creds.get("name") != "ghcr-saveiq"
        ):
            fail(
                f"{name} must use the ghcr-saveiq registry credential", profile=profile
            )

        image_url = image["url"]
        if "@sha256:" not in image_url:
            fail(f"{name} image must be pinned by sha256 digest", profile=profile)
        if not allow_placeholders and not DIGEST_PATTERN.search(image_url):
            fail(
                f"{name} image digest must be a 64-character sha256 digest",
                profile=profile,
            )

    redis = services[PROFILES[profile]["redis"]]
    if PROFILES[profile]["paid_plans"] and redis.get("plan") in {None, "free"}:
        fail(
            f"{PROFILES[profile]['redis']} must use a paid plan (not free)",
            profile=profile,
        )


def validate_env(
    services: dict[str, dict[str, Any]],
    *,
    profile: str,
    allow_live_ai: bool = False,
    allow_neural_bandit: bool = False,
    allow_rlhf_router: bool = False,
    allow_rlhf_after_neural: bool = False,
) -> None:
    api_name = PROFILES[profile]["api"]
    web_name = PROFILES[profile]["web"]
    api_env = env_map(services[api_name], profile=profile)
    web_env = env_map(services[web_name], profile=profile)

    api_command = services[api_name].get("dockerCommand")
    if api_command != "python -m app.server":
        fail(
            "API service must use the Render-friendly Python startup entrypoint",
            profile=profile,
        )

    admin_token = api_env.get("ADMIN_API_TOKEN")
    if admin_token is None or admin_token.get("sync") is not False:
        fail("ADMIN_API_TOKEN must be sync: false", profile=profile)

    if (
        api_env.get("DATABASE_URL", {}).get("fromDatabase", {}).get("name")
        != PROFILES[profile]["postgres"]
    ):
        fail(
            f"API DATABASE_URL must come from {PROFILES[profile]['postgres']}",
            profile=profile,
        )

    if (
        api_env.get("REDIS_URL", {}).get("fromService", {}).get("name")
        != PROFILES[profile]["redis"]
    ):
        fail(
            f"API REDIS_URL must come from {PROFILES[profile]['redis']}",
            profile=profile,
        )

    if api_env.get("ENVIRONMENT", {}).get("value") != PROFILES[profile]["environment"]:
        fail(
            f"API ENVIRONMENT must be {PROFILES[profile]['environment']}",
            profile=profile,
        )

    for flag in (
        "FEATURE_BANDIT_ROUTER",
        "FEATURE_PERSONALIZATION",
        "FEATURE_NEURAL_BANDIT",
        "FEATURE_RLHF_ROUTER",
        "FEATURE_AUTO_TUNING",
        "FEATURE_KILL_SWITCH",
    ):
        if flag in api_env and api_env[flag].get("value") not in {None, "false"}:
            if flag == "FEATURE_NEURAL_BANDIT" and allow_neural_bandit:
                continue
            if flag == "FEATURE_RLHF_ROUTER" and allow_rlhf_router:
                continue
            # Staging may omit FEATURE_AUTO_TUNING; production must keep listed flags false when present.
            if profile == "production" or flag not in {
                "FEATURE_AUTO_TUNING",
                "FEATURE_KILL_SWITCH",
            }:
                if api_env[flag].get("value") != "false":
                    fail(f"{flag} must be false in {profile}", profile=profile)

    if allow_neural_bandit and allow_rlhf_router and not allow_rlhf_after_neural:
        fail(
            "allow only one of --allow-neural-bandit / --allow-rlhf-router "
            "(pass --allow-rlhf-after-neural only after prod neural n100)",
            profile=profile,
        )
    if allow_rlhf_after_neural and not (allow_neural_bandit and allow_rlhf_router):
        fail(
            "--allow-rlhf-after-neural requires both --allow-neural-bandit and --allow-rlhf-router",
            profile=profile,
        )
    if allow_rlhf_after_neural and profile != "production":
        fail("--allow-rlhf-after-neural is production-only", profile=profile)

    if allow_neural_bandit:
        neural = (api_env.get("FEATURE_NEURAL_BANDIT") or {}).get("value")
        if neural not in {None, "false", "true"}:
            fail("FEATURE_NEURAL_BANDIT must be false|true", profile=profile)
        if not allow_rlhf_after_neural:
            rlhf = (api_env.get("FEATURE_RLHF_ROUTER") or {}).get("value")
            if rlhf not in {None, "false"}:
                fail(
                    "FEATURE_RLHF_ROUTER must stay false while FEATURE_NEURAL_BANDIT is allowed",
                    profile=profile,
                )

    if allow_rlhf_router:
        rlhf = (api_env.get("FEATURE_RLHF_ROUTER") or {}).get("value")
        if rlhf not in {None, "false", "true"}:
            fail("FEATURE_RLHF_ROUTER must be false|true", profile=profile)
        if not allow_rlhf_after_neural:
            neural = (api_env.get("FEATURE_NEURAL_BANDIT") or {}).get("value")
            if neural not in {None, "false"}:
                fail(
                    "FEATURE_NEURAL_BANDIT must stay false while FEATURE_RLHF_ROUTER is allowed",
                    profile=profile,
                )

    # Gate 10F/10G: FEATURE_AI_ROUTER=true with mode mock|live.
    # Chinese providers only with live. Staging stays mock unless --allow-live-ai.
    ai_router = (api_env.get("FEATURE_AI_ROUTER") or {}).get("value")
    ai_mode = str((api_env.get("AI_ROUTER_MODE") or {}).get("value") or "").lower()
    chinese = (api_env.get("FEATURE_CHINESE_LLM_PROVIDERS") or {}).get("value")
    if ai_router not in {None, "false", "true"}:
        fail("FEATURE_AI_ROUTER must be false|true", profile=profile)
    if chinese not in {None, "false", "true"}:
        fail("FEATURE_CHINESE_LLM_PROVIDERS must be false|true", profile=profile)

    allow_live = allow_live_ai or profile == "production"
    if allow_live:
        if ai_router == "true" and ai_mode not in {"mock", "live", "disabled"}:
            fail(
                "FEATURE_AI_ROUTER=true requires AI_ROUTER_MODE=mock|live|disabled",
                profile=profile,
            )
        if ai_mode == "live" and ai_router != "true":
            fail("AI_ROUTER_MODE=live requires FEATURE_AI_ROUTER=true", profile=profile)
        if chinese == "true" and ai_mode != "live":
            fail(
                "FEATURE_CHINESE_LLM_PROVIDERS=true requires AI_ROUTER_MODE=live",
                profile=profile,
            )
    else:
        if ai_router == "true" and ai_mode not in {"mock", "disabled"}:
            fail(
                "FEATURE_AI_ROUTER=true requires AI_ROUTER_MODE=mock "
                "(pass --allow-live-ai for live enablement)",
                profile=profile,
            )
        if chinese not in {None, "false"}:
            fail(
                "FEATURE_CHINESE_LLM_PROVIDERS must be false "
                "(pass --allow-live-ai for Gate 10G)",
                profile=profile,
            )
        if ai_mode == "live":
            fail("staging must not set AI_ROUTER_MODE=live", profile=profile)

    if profile == "production":
        for flag in (
            "FEATURE_AI_ROUTER",
            "FEATURE_BANDIT_ROUTER",
            "FEATURE_PERSONALIZATION",
            "FEATURE_CHINESE_LLM_PROVIDERS",
            "FEATURE_AUTO_TUNING",
            "FEATURE_KILL_SWITCH",
            "RATE_LIMIT_ENABLED",
        ):
            if flag not in api_env:
                fail(f"production API must set {flag}", profile=profile)
        if "AI_ROUTER_MODE" not in api_env:
            fail("production API must set AI_ROUTER_MODE", profile=profile)
        if api_env.get("RATE_LIMIT_ENABLED", {}).get("value") != "true":
            fail("production RATE_LIMIT_ENABLED must be true", profile=profile)
        if web_env.get("PRODUCTION_NOINDEX", {}).get("value") != "true":
            fail("web service must set PRODUCTION_NOINDEX=true", profile=profile)
    else:
        if web_env.get("STAGING_NOINDEX", {}).get("value") != "true":
            fail("web service must set STAGING_NOINDEX=true", profile=profile)

    if web_env.get("NEXT_PUBLIC_BRAND_NAME", {}).get("value") != "DealHunter":
        fail("web service must set NEXT_PUBLIC_BRAND_NAME=DealHunter", profile=profile)


def validate_database(data: dict[str, Any], *, profile: str) -> None:
    databases = data.get("databases")
    if not isinstance(databases, list):
        fail("databases must be a list", profile=profile)

    names = {
        database.get("name") for database in databases if isinstance(database, dict)
    }
    missing = PROFILES[profile]["databases"] - names
    if missing:
        fail(f"missing databases: {', '.join(sorted(missing))}", profile=profile)

    if PROFILES[profile]["paid_plans"]:
        for database in databases:
            if not isinstance(database, dict):
                continue
            if database.get("name") != PROFILES[profile]["postgres"]:
                continue
            if database.get("plan") in {None, "free"}:
                fail(
                    f"{PROFILES[profile]['postgres']} must use a paid plan (not free)",
                    profile=profile,
                )


def detect_profile(path: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    name = path.name.lower()
    if "production" in name:
        return "production"
    return "staging"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--allow-placeholders", action="store_true")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default=None,
        help="Blueprint profile (default: detect from filename)",
    )
    parser.add_argument(
        "--allow-live-ai",
        action="store_true",
        help="Gate 10G: allow AI_ROUTER_MODE=live and FEATURE_CHINESE_LLM_PROVIDERS=true",
    )
    parser.add_argument(
        "--allow-neural-bandit",
        action="store_true",
        help="Gate 10H: allow FEATURE_NEURAL_BANDIT=true (RLHF stays false)",
    )
    parser.add_argument(
        "--allow-rlhf-router",
        action="store_true",
        help="Gate 10H: allow FEATURE_RLHF_ROUTER=true (neural stays false unless after-neural)",
    )
    parser.add_argument(
        "--allow-rlhf-after-neural",
        action="store_true",
        help="Production only: allow both FEATURE_NEURAL_BANDIT and FEATURE_RLHF_ROUTER after n100",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = detect_profile(args.blueprint, args.profile)
    raw, data = load_blueprint(args.blueprint, profile=profile)

    if not args.allow_placeholders and PLACEHOLDER_PATTERN.search(raw):
        fail(
            "replace all <PLACEHOLDER> values before applying the Blueprint",
            profile=profile,
        )

    services = service_by_name(data, profile=profile)
    validate_services(
        services,
        profile=profile,
        allow_placeholders=args.allow_placeholders,
    )
    validate_env(
        services,
        profile=profile,
        allow_live_ai=args.allow_live_ai,
        allow_neural_bandit=args.allow_neural_bandit,
        allow_rlhf_router=args.allow_rlhf_router,
        allow_rlhf_after_neural=args.allow_rlhf_after_neural,
    )
    validate_database(data, profile=profile)

    if args.allow_placeholders:
        print(PROFILES[profile]["ok_template"])
    else:
        print(PROFILES[profile]["ok"])


if __name__ == "__main__":
    main()
