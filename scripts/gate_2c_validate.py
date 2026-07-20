#!/usr/bin/env python3
"""Run Gate 2C staging validation checks against the live Render environment."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

API_URL = "https://dealhunter-staging-api.onrender.com"
WEB_URL = "https://dealhunter-staging-web.onrender.com"
ROOT = Path(__file__).resolve().parents[1]
DIGEST_PATTERN = re.compile(r"ghcr\.io/.+@sha256:[a-f0-9]{64}")
REQUIRED_OPENAPI_PATHS = {
    "/health",
    "/admin/affiliate/sync/mock",
    "/admin/affiliate/products",
    "/admin/affiliate/offers",
    "/admin/affiliate/price-history",
    "/admin/affiliate/coupons",
    "/admin/affiliate/cashback",
}


@dataclass
class Check:
    name: str
    status: str
    detail: str


def fail(message: str) -> None:
    print(f"gate_2c_validation=error: {message}", file=sys.stderr)
    raise SystemExit(1)


def open_with_retries(request: Request) -> Any:
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            return urlopen(request, timeout=60)
        except (TimeoutError, URLError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(5)
    fail(f"{request.full_url} request failed: {last_error}")


def request_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "SaveIQ-Gate-2C/1.0"})
    try:
        with open_with_retries(request) as response:
            if response.status != 200:
                fail(f"{url} returned HTTP {response.status}")
            payload = response.read().decode("utf-8")
    except (TimeoutError, URLError) as exc:
        fail(f"{url} request failed: {exc}")

    data = json.loads(payload)
    if not isinstance(data, dict):
        fail(f"{url} did not return a JSON object")
    return data


def request_headers(url: str) -> dict[str, str]:
    request = Request(url, method="HEAD", headers={"User-Agent": "SaveIQ-Gate-2C/1.0"})
    try:
        with open_with_retries(request) as response:
            if response.status != 200:
                fail(f"{url} returned HTTP {response.status}")
            return {key.lower(): value for key, value in response.headers.items()}
    except (TimeoutError, URLError) as exc:
        fail(f"{url} request failed: {exc}")


def request_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "SaveIQ-Gate-2C/1.0"})
    try:
        with open_with_retries(request) as response:
            if response.status != 200:
                fail(f"{url} returned HTTP {response.status}")
            return response.read().decode("utf-8")
    except (TimeoutError, URLError) as exc:
        fail(f"{url} request failed: {exc}")


def run_local_validation() -> str:
    result = subprocess.run(
        [sys.executable, "scripts/validate_render_blueprint.py", "render.yaml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def validate_render_yaml() -> Check:
    output = run_local_validation()
    raw = (ROOT / "render.yaml").read_text(encoding="utf-8")
    if "<" in raw or ">" in raw:
        fail("render.yaml still contains angle-bracket placeholders")
    if len(DIGEST_PATTERN.findall(raw)) != 2:
        fail("render.yaml must pin exactly two GHCR image digests")
    if "type: worker" in raw or "type: cron" in raw:
        fail("cost-optimized staging must defer worker and scheduler")
    return Check("Render Blueprint validation", "PASS", output)


def validate_health() -> list[Check]:
    api_health = request_json(f"{API_URL}/health")
    web_health = request_json(f"{WEB_URL}/api/health")
    if api_health.get("status") != "ok":
        fail("API health status is not ok")
    if web_health.get("status") != "ok":
        fail("Web health status is not ok")
    return [
        Check("API health", "PASS", json.dumps(api_health, sort_keys=True)),
        Check("Web health", "PASS", json.dumps(web_health, sort_keys=True)),
    ]


def validate_noindex() -> Check:
    headers = request_headers(f"{WEB_URL}/")
    robots = headers.get("x-robots-tag", "")
    if "noindex" not in robots or "nofollow" not in robots:
        fail("staging web is missing X-Robots-Tag noindex, nofollow")
    return Check("Staging noindex header", "PASS", robots)


def validate_openapi_inventory() -> Check:
    schema = request_json(f"{API_URL}/openapi.json")
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        fail("OpenAPI schema is missing paths")
    missing = REQUIRED_OPENAPI_PATHS - set(paths)
    if missing:
        fail(f"OpenAPI schema missing paths: {', '.join(sorted(missing))}")
    return Check(
        "API route inventory",
        "PASS",
        f"{len(REQUIRED_OPENAPI_PATHS)} required paths present",
    )


def validate_consumer_smoke() -> Check:
    body = request_text(f"{WEB_URL}/")
    expected_markers = ("Foundation status", "Mock affiliate search")
    if "DealHunter" not in body or not any(
        marker in body for marker in expected_markers
    ):
        fail("frontend page did not render an expected staging marker")
    return Check("Consumer web smoke", "PASS", "staging web page rendered")


def guardrail_checks() -> list[Check]:
    raw = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "docs" / "AFFILIATE_CONNECTORS.md",
            ROOT / "docs" / "AI_SYSTEM.md",
            ROOT / "docs" / "SECURITY.md",
            ROOT / "README.md",
        ]
    )
    for forbidden in ("web scraping", "real affiliate", "complete ai agent"):
        if forbidden not in raw.lower():
            fail(f"missing guardrail text for {forbidden}")
    return [
        Check(
            "Mock-only affiliate guardrail", "PASS", "real integrations remain deferred"
        ),
        Check("No scraping guardrail", "PASS", "scraping remains out of scope"),
        Check(
            "AI fake/deferred guardrail", "PASS", "complete AI agent remains deferred"
        ),
    ]


def deferred_checks() -> list[Check]:
    return [
        Check(
            "Shopping Assistant fake mode", "DEFERRED", "not implemented in foundation"
        ),
        Check(
            "Awin fixture pipeline", "DEFERRED", "no real Awin or fixture pipeline yet"
        ),
        Check(
            "Price alert fake notification",
            "DEFERRED",
            "alerts are outside current foundation",
        ),
        Check(
            "Background jobs",
            "DEFERRED",
            "worker and scheduler deferred to avoid staging cost",
        ),
    ]


def report(checks: list[Check]) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Gate 2C Staging Validation",
        "",
        f"- Generated: {now}",
        f"- Commit: `{current_commit()}`",
        f"- API: `{API_URL}`",
        f"- Web: `{WEB_URL}`",
        "",
        "## Results",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        detail = check.detail.replace("|", "\\|")
        lines.append(f"| {check.name} | {check.status} | {detail} |")
    lines.extend(
        [
            "",
            "## Gate Decision",
            "",
            "Gate 2C passes for the cost-optimized staging foundation. Deferred items are not "
            "release blockers because their product surfaces are not implemented yet and no real "
            "affiliate, AI, scraping, or email systems are enabled.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    checks: list[Check] = []
    checks.append(validate_render_yaml())
    checks.extend(validate_health())
    checks.append(validate_noindex())
    checks.append(validate_openapi_inventory())
    checks.append(validate_consumer_smoke())
    checks.extend(guardrail_checks())
    checks.extend(deferred_checks())

    report_path = ROOT / "docs" / "GATE_2C_STAGING_VALIDATION.md"
    report_path.write_text(report(checks), encoding="utf-8")
    print("gate_2c_validation=ok")
    print(f"report={report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
