#!/usr/bin/env python3
"""Seed staging with deterministic mock affiliate data and verify search."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_API_URL = "https://dealhunter-staging-api.onrender.com"
DEFAULT_WEB_URL = "https://dealhunter-staging-web.onrender.com"


def fail(message: str) -> None:
    print(f"staging_mock_seed=error: {message}", file=sys.stderr)
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


def post_mock_sync(api_url: str, token: str) -> dict[str, Any]:
    request = Request(
        f"{api_url.rstrip('/')}/admin/affiliate/sync/mock",
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Length": "0",
            "User-Agent": "SaveIQ-Staging-Seed/1.0",
            "X-Admin-Token": token,
        },
    )
    return read_json(request)


def get_search(url: str, query: str) -> dict[str, Any]:
    request = Request(
        f"{url.rstrip('/')}/search?q={query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "SaveIQ-Staging-Seed/1.0",
        },
    )
    return read_json(request)


def get_web_search(web_url: str, query: str) -> dict[str, Any]:
    request = Request(
        f"{web_url.rstrip('/')}/api/search?q={query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "SaveIQ-Staging-Seed/1.0",
        },
    )
    return read_json(request)


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
    token = os.environ.get(args.token_env)
    if not token:
        fail(f"set {args.token_env} before running this script")

    sync_result = post_mock_sync(args.api_url, token)
    stats = sync_result.get("stats")
    if not isinstance(stats, dict):
        fail("mock sync response did not include stats")
    if sync_result.get("status") not in {"completed", "completed_with_errors"}:
        fail(f"mock sync did not complete successfully: {sync_result.get('status')}")

    api_search = get_search(args.api_url, args.query)
    web_search = get_web_search(args.web_url, args.query)
    api_count = api_search.get("count")
    web_count = web_search.get("count")
    if not isinstance(api_count, int) or api_count < 1:
        fail(f"API search returned no results for query {args.query!r}")
    if not isinstance(web_count, int) or web_count < 1:
        fail(f"web search proxy returned no results for query {args.query!r}")

    print("staging_mock_seed=ok")
    print(f"sync_status={sync_result['status']}")
    print(f"received={stats.get('received')}")
    print(f"api_search_count={api_count}")
    print(f"web_search_count={web_count}")


if __name__ == "__main__":
    main()
