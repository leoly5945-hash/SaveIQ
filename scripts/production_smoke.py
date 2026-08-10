#!/usr/bin/env python3
"""Lightweight production smoke checks (Gate 10A).

Verifies public health surfaces and that advanced feature flags remain disabled.
Admin checks run only when ADMIN_API_TOKEN is set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_API_URL = "https://dealhunter-production-api.onrender.com"
DEFAULT_WEB_URL = "https://dealhunter-production-web.onrender.com"
USER_AGENT = "SaveIQ-Production-Smoke/1.0"


@dataclass(frozen=True)
class Check:
    name: str
    detail: str


def fail(message: str) -> None:
    print(f"production_smoke=error: {message}", file=sys.stderr)
    raise SystemExit(1)


def open_with_retries(request: Request, *, attempts: int = 3) -> Any:
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return urlopen(request, timeout=60)
        except (TimeoutError, URLError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(5)
    fail(f"{request.full_url} request failed: {last_error}")


def request_json(request: Request, *, expected_status: int = 200) -> dict[str, Any]:
    try:
        with open_with_retries(request) as response:
            payload = response.read().decode("utf-8")
            if response.status != expected_status:
                fail(
                    f"{request.full_url} returned HTTP {response.status}; "
                    f"expected {expected_status}: {payload}"
                )
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == expected_status:
            payload = detail
        else:
            fail(
                f"{request.full_url} returned HTTP {exc.code}; "
                f"expected {expected_status}: {detail}"
            )
    data = json.loads(payload)
    if not isinstance(data, dict):
        fail(f"{request.full_url} did not return a JSON object")
    return data


def get_json(url: str, token: str | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["X-Admin-Token"] = token
    return request_json(Request(url, headers=headers))


def get_headers(url: str) -> dict[str, str]:
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with open_with_retries(request) as response:
        return {k.lower(): v for k, v in response.headers.items()}


def get_text(url: str, token: str | None = None) -> str:
    headers = {"Accept": "text/plain", "User-Agent": USER_AGENT}
    metrics_token = os.environ.get("METRICS_TOKEN")
    if metrics_token:
        headers["X-Metrics-Token"] = metrics_token
    if token:
        headers["X-Admin-Token"] = token
    request = Request(url, headers=headers)
    with open_with_retries(request) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_API_URL))
    parser.add_argument("--web-url", default=os.environ.get("WEB_URL", DEFAULT_WEB_URL))
    parser.add_argument(
        "--require-admin",
        action="store_true",
        help="Fail if ADMIN_API_TOKEN is missing (default: skip admin checks).",
    )
    parser.add_argument(
        "--allow-active-canary",
        action="store_true",
        help=(
            "Do not fail when canary is enabled/percentage>0, and allow "
            "canary-effective bandit/router/personalization (logging/mock only; "
            "still fail on controls_routing or live router unless --allow-live-router)."
        ),
    )
    parser.add_argument(
        "--allow-live-router",
        action="store_true",
        help="Gate 10G: allow AI router mode=live (still requires intentional enablement).",
    )
    parser.add_argument(
        "--allow-chinese-providers",
        action="store_true",
        help="Gate 10G: allow chinese_providers_enabled=true.",
    )
    args = parser.parse_args()
    api_url = args.api_url.rstrip("/")
    web_url = args.web_url.rstrip("/")
    token = os.environ.get("ADMIN_API_TOKEN")
    if args.require_admin and not token:
        fail("set ADMIN_API_TOKEN before running with --require-admin")

    checks: list[Check] = []

    api_health = get_json(f"{api_url}/health")
    if api_health.get("status") != "ok":
        fail("API health is not ok")
    checks.append(Check("api_health", "ok"))

    web_health = get_json(f"{web_url}/api/health")
    if web_health.get("status") != "ok":
        fail("web health is not ok")
    checks.append(Check("web_health", "ok"))

    robots = get_headers(f"{web_url}/api/health").get("x-robots-tag", "")
    if "noindex" not in robots.lower():
        fail("production web must send X-Robots-Tag noindex until public launch")
    checks.append(Check("production_noindex", robots or "present"))

    bandit = get_json(f"{api_url}/bandit/status")
    # At canary >0%, sticky cohort can enable bandit logging (active=true, mode=logging)
    # without global FEATURE_BANDIT_ROUTER. At C4 (100%) every request is canary.
    if bandit.get("controls_routing") is True:
        fail(
            "bandit must not control routing in production until intentionally enabled"
        )
    if not args.allow_active_canary and bandit.get("active") is True:
        fail("bandit must remain inactive/disabled in production Gate 10A")
    checks.append(
        Check(
            "bandit_status",
            f"active={bandit.get('active')} mode={bandit.get('mode')} "
            f"controls_routing={bandit.get('controls_routing')}",
        )
    )

    personalization = get_json(f"{api_url}/personalization/status")
    if personalization.get("feature_enabled") is True and not args.allow_active_canary:
        fail("personalization must remain disabled in production Gate 10A")
    checks.append(
        Check(
            "personalization_status",
            f"enabled={personalization.get('feature_enabled')}",
        )
    )

    search = get_json(f"{api_url}/search?{urlencode({'q': 'laptop', 'limit': '5'})}")
    if not isinstance(search.get("count"), int):
        fail("search returned malformed payload")
    checks.append(Check("api_search", f"count={search['count']}"))

    metrics_body = get_text(f"{api_url}/metrics", token)
    if "http_requests_total" not in metrics_body:
        fail("Prometheus /metrics missing http_requests_total")
    if "http_request_duration_seconds" not in metrics_body:
        fail("Prometheus /metrics missing http_request_duration_seconds")
    checks.append(Check("prometheus_metrics", "http_requests_total+duration"))

    if token:
        router = get_json(f"{api_url}/admin/router-status", token)
        router_mode = str(router.get("mode") or "").lower()
        # Canary-effective or Gate 10F global mock may show active=true with mode=mock.
        if router_mode == "live" and not args.allow_live_router:
            fail("AI router must not be live in production until intentionally enabled")
        if (
            router.get("active") is True
            and router_mode not in {"mock", "live"}
            and not args.allow_active_canary
        ):
            fail("AI router must remain inactive in production Gate 10A")
        if router.get("active") is True and router_mode == "live" and not args.allow_live_router:
            fail("AI router live mode requires --allow-live-router")
        checks.append(
            Check(
                "ai_router_status",
                f"active={router.get('active')} mode={router.get('mode')}",
            )
        )

        models = get_json(f"{api_url}/admin/models/status", token)
        chinese = models.get("chinese_providers_enabled")
        if chinese is True and not args.allow_chinese_providers:
            fail("Chinese LLM providers must remain disabled in production Gate 10A")
        checks.append(Check("admin_models_status", f"chinese={chinese}"))

        rate = get_json(f"{api_url}/admin/rate-limit/status", token)
        if rate.get("enabled") is not True:
            fail("production rate limiting must be enabled")
        checks.append(
            Check(
                "rate_limit_status",
                (
                    f"enabled={rate.get('enabled')} "
                    f"public={rate.get('public_per_minute')} "
                    f"store={rate.get('store')}"
                ),
            )
        )

        canary = get_json(f"{api_url}/admin/canary/status", token)
        canary_on = (
            canary.get("enabled") is True or int(canary.get("percentage") or 0) > 0
        )
        if canary_on and not args.allow_active_canary:
            fail(
                "canary must remain disabled (enabled=false, percentage=0) "
                "until an intentional Gate 10C phase "
                "(or pass --allow-active-canary)"
            )
        checks.append(
            Check(
                "canary_status",
                f"enabled={canary.get('enabled')} percentage={canary.get('percentage')}",
            )
        )
        canary_stats = get_json(f"{api_url}/admin/canary/stats", token)
        if "assignments" not in canary_stats:
            fail("canary stats missing assignments")
        checks.append(Check("canary_stats", "ok"))

        abtest = get_json(f"{api_url}/admin/abtest/status", token)
        if abtest.get("feature_enabled") is True or abtest.get("running") is True:
            fail(
                "A/B testing must remain disabled "
                "(FEATURE_ABTEST_ENABLED=false / not running) until intentional Gate 10D"
            )
        checks.append(
            Check(
                "abtest_status",
                (
                    f"feature_enabled={abtest.get('feature_enabled')} "
                    f"running={abtest.get('running')}"
                ),
            )
        )

        safety = get_json(f"{api_url}/admin/safety/status", token)
        runtime = safety.get("runtime") or {}
        env = safety.get("env") or {}
        if (
            env.get("feature_kill_switch") is True
            or env.get("feature_auto_tuning") is True
        ):
            fail(
                "Gate 10E safety features must remain env-disabled "
                "(FEATURE_KILL_SWITCH=false, FEATURE_AUTO_TUNING=false) until staging drill"
            )
        if runtime.get("tripped") is True:
            fail(
                "kill switch is tripped; disarm or investigate before declaring smoke ok"
            )
        checks.append(
            Check(
                "safety_status",
                (
                    f"kill={env.get('feature_kill_switch')} "
                    f"autotune={env.get('feature_auto_tuning')} "
                    f"tripped={runtime.get('tripped')}"
                ),
            )
        )
    else:
        checks.append(Check("admin_checks", "skipped=no_ADMIN_API_TOKEN"))

    print("production_smoke=ok")
    for check in checks:
        print(f"{check.name}={check.detail}")


if __name__ == "__main__":
    main()
