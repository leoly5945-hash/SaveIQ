#!/usr/bin/env python3
"""Run an end-to-end smoke test against the live staging environment."""

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

DEFAULT_API_URL = "https://dealhunter-staging-api.onrender.com"
DEFAULT_WEB_URL = "https://dealhunter-staging-web.onrender.com"
USER_AGENT = "SaveIQ-Staging-Smoke/1.0"


@dataclass(frozen=True)
class Check:
    name: str
    detail: str


def fail(message: str) -> None:
    print(f"staging_smoke=error: {message}", file=sys.stderr)
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


def post_json(
    url: str, payload: dict[str, Any], token: str | None = None
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["X-Admin-Token"] = token
    return request_json(Request(url, data=body, headers=headers, method="POST"))


def post_empty(url: str, token: str) -> dict[str, Any]:
    return request_json(
        Request(
            url,
            data=b"",
            headers={
                "Accept": "application/json",
                "Content-Length": "0",
                "User-Agent": USER_AGENT,
                "X-Admin-Token": token,
            },
            method="POST",
        )
    )


def get_json(url: str, token: str | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["X-Admin-Token"] = token
    return request_json(Request(url, headers=headers))


def search_url(base_url: str, path: str, **params: str) -> str:
    return f"{base_url.rstrip('/')}{path}?{urlencode(params)}"


def require_count(payload: dict[str, Any], label: str) -> list[dict[str, Any]]:
    count = payload.get("count")
    results = payload.get("results")
    if not isinstance(count, int) or count < 1 or not isinstance(results, list):
        fail(f"{label} returned no results")
    if not all(isinstance(result, dict) for result in results):
        fail(f"{label} returned malformed results")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--query", default="buds")
    parser.add_argument(
        "--token-env",
        default="ADMIN_API_TOKEN",
        help="Environment variable containing the staging admin token.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_url = args.api_url.rstrip("/")
    web_url = args.web_url.rstrip("/")
    token = os.environ.get(args.token_env)
    if not token:
        fail(f"set {args.token_env} before running this script")

    checks: list[Check] = []

    api_health = get_json(f"{api_url}/health")
    if api_health.get("status") != "ok":
        fail("API health status is not ok")
    checks.append(Check("api_health", "ok"))

    web_health = get_json(f"{web_url}/api/health")
    if web_health.get("status") != "ok":
        fail("web health status is not ok")
    checks.append(Check("web_health", "ok"))

    sync_result = post_empty(f"{api_url}/admin/affiliate/sync/mock", token)
    if sync_result.get("status") not in {"completed", "completed_with_errors"}:
        fail(f"mock sync failed: {sync_result.get('status')}")
    stats = sync_result.get("stats")
    if not isinstance(stats, dict) or stats.get("received") != 12:
        fail("mock sync did not receive the expected 12 records")
    checks.append(Check("mock_sync", str(sync_result["status"])))

    summary = get_json(f"{api_url}/admin/affiliate/staging-summary", token)
    counts = summary.get("counts")
    if not isinstance(counts, dict):
        fail("staging summary is missing counts")
    if counts.get("products", 0) < 5 or counts.get("offers", 0) < 6:
        fail(f"staging summary counts look wrong: {counts}")
    checks.append(Check("admin_summary", f"offers={counts.get('offers')}"))

    api_search = get_json(
        search_url(api_url, "/search", q=args.query, sort="clicks_desc")
    )
    api_results = require_count(api_search, "API search")
    first_offer = api_results[0]
    offer_id = first_offer.get("offer_id")
    if not isinstance(offer_id, int):
        fail("API search result is missing offer_id")
    if "ranking_reasons" not in first_offer:
        fail("API search result is missing ranking_reasons")
    checks.append(Check("api_search", f"count={api_search['count']}"))

    web_search = get_json(
        search_url(web_url, "/api/search", q=args.query, sort="clicks_desc")
    )
    require_count(web_search, "web search proxy")
    checks.append(Check("web_search_proxy", f"count={web_search['count']}"))

    click = post_json(
        f"{api_url}/clicks",
        {"offer_id": offer_id, "target_type": "product", "referrer": "staging-smoke"},
    )
    if click.get("offer_id") != offer_id:
        fail("click tracking response did not echo the tracked offer")
    checks.append(Check("click_tracking", f"offer_id={offer_id}"))

    web_click = post_json(
        f"{web_url}/api/clicks",
        {"offer_id": offer_id, "target_type": "affiliate", "referrer": "staging-smoke"},
    )
    if web_click.get("offer_id") != offer_id:
        fail("web click proxy response did not echo the tracked offer")
    checks.append(Check("web_click_proxy", f"offer_id={offer_id}"))

    analytics = get_json(f"{api_url}/admin/affiliate/click-analytics", token)
    if (
        not isinstance(analytics.get("total_clicks"), int)
        or analytics["total_clicks"] < 1
    ):
        fail("click analytics did not include tracked clicks")
    checks.append(Check("click_analytics", f"total={analytics['total_clicks']}"))

    web_summary = post_json(
        f"{web_url}/api/admin/staging-summary", {"adminToken": token}
    )
    web_counts = web_summary.get("counts")
    if not isinstance(web_counts, dict) or web_counts.get("offers", 0) < 6:
        fail("web staging summary proxy returned unexpected counts")
    checks.append(
        Check("web_admin_summary_proxy", f"offers={web_counts.get('offers')}")
    )

    web_analytics = post_json(
        f"{web_url}/api/admin/click-analytics", {"adminToken": token}
    )
    if not isinstance(web_analytics.get("total_clicks"), int):
        fail("web click analytics proxy returned malformed data")
    checks.append(
        Check("web_click_analytics_proxy", f"total={web_analytics['total_clicks']}")
    )

    print("staging_smoke=ok")
    for check in checks:
        print(f"{check.name}={check.detail}")


if __name__ == "__main__":
    main()
