#!/usr/bin/env python3
"""Ingest the curated real Amazon.ca deal set and verify it is live.

Unlike ``staging_seed_mock.py`` (deterministic fixtures), this drives the
``/admin/affiliate/sync/curated`` endpoint, which ingests the version-controlled
``apps/api/app/services/affiliate/curated_deals.json`` catalogue. It is safe to
run against production - the data is real, hand-checked products and the sync is
idempotent (re-running refreshes prices/titles in place).

Usage:
    ADMIN_API_TOKEN=... python scripts/seed_curated_deals.py \\
        --api-url https://dealhunter-production-api.onrender.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_API_URL = "https://dealhunter-staging-api.onrender.com"


def fail(message: str) -> None:
    print(f"curated_seed=error: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_json(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
            if response.status < 200 or response.status >= 300:
                fail(f"{request.full_url} returned HTTP {response.status}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"{request.full_url} returned HTTP {exc.code}: {detail}")
    except (TimeoutError, URLError) as exc:
        fail(f"{request.full_url} request failed: {exc}")

    data = json.loads(payload)
    if not isinstance(data, dict):
        fail(f"{request.full_url} did not return a JSON object")
    return data


def post_curated_sync(api_url: str, token: str) -> dict[str, Any]:
    request = Request(
        f"{api_url.rstrip('/')}/admin/affiliate/sync/curated",
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Length": "0",
            "User-Agent": "SaveIQ-Curated-Seed/1.0",
            "X-Admin-Token": token,
        },
    )
    return read_json(request)


def get_featured_deals(api_url: str) -> dict[str, Any]:
    request = Request(
        f"{api_url.rstrip('/')}/featured-deals",
        headers={
            "Accept": "application/json",
            "User-Agent": "SaveIQ-Curated-Seed/1.0",
        },
    )
    return read_json(request)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument(
        "--token-env",
        default="ADMIN_API_TOKEN",
        help="Environment variable holding the admin token for the target API.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        fail(f"set {args.token_env} before running this script")

    sync_result = post_curated_sync(args.api_url, token)
    stats = sync_result.get("stats")
    if not isinstance(stats, dict):
        fail("curated sync response did not include stats")
    if sync_result.get("status") not in {"completed", "completed_with_errors"}:
        fail(f"curated sync did not complete successfully: {sync_result.get('status')}")

    featured = get_featured_deals(args.api_url)
    count = featured.get("count")
    if not isinstance(count, int) or count < 1:
        fail("/featured-deals returned no deals after the sync")

    print("curated_seed=ok")
    print(f"sync_status={sync_result['status']}")
    print(f"received={stats.get('received')}")
    print(f"inserted={stats.get('inserted')}")
    print(f"updated={stats.get('updated')}")
    print(f"rejected={stats.get('rejected')}")
    print(f"featured_deal_count={count}")


if __name__ == "__main__":
    main()
