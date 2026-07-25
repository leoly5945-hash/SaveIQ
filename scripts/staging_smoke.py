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
    url: str,
    payload: dict[str, Any],
    token: str | None = None,
    *,
    expected_status: int = 200,
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
    return request_json(
        Request(url, data=body, headers=headers, method="POST"),
        expected_status=expected_status,
    )


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


def require_recommendation_explanation(
    recommendation: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    explanation = recommendation.get("decision_explanation")
    if not isinstance(explanation, dict):
        fail(f"{label} is missing decision_explanation")
    summary = explanation.get("summary")
    matched_intent = explanation.get("matched_intent")
    ranking_signals = explanation.get("ranking_signals")
    guardrails = explanation.get("guardrails")
    if not isinstance(summary, str) or not summary:
        fail(f"{label} explanation is missing summary")
    if not isinstance(matched_intent, list) or not matched_intent:
        fail(f"{label} explanation is missing matched intent signals")
    if not isinstance(ranking_signals, list) or not ranking_signals:
        fail(f"{label} explanation is missing ranking signals")
    if not isinstance(guardrails, list):
        fail(f"{label} explanation is missing guardrails")
    if "no model call" not in guardrails or "no web scraping" not in guardrails:
        fail(f"{label} explanation is missing staging guardrails")
    return explanation


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

    recommendation_payload = {
        "intent": f"Find fresh {args.query} with a coupon",
        "limit": 3,
    }
    api_recommendations = post_json(
        f"{api_url}/recommendations", recommendation_payload
    )
    api_recommendation_count = api_recommendations.get("count")
    if not isinstance(api_recommendation_count, int) or api_recommendation_count < 1:
        fail("API recommendations returned malformed count")
    if api_recommendations.get("strategy") != "rule_based_mock_v0":
        fail("API recommendations returned unexpected strategy")
    trace_event_id = api_recommendations.get("trace_event_id")
    if not isinstance(trace_event_id, int):
        fail("API recommendations did not return a trace_event_id")
    trace = api_recommendations.get("evaluation_trace")
    if not isinstance(trace, list) or len(trace) < 3:
        fail("API recommendations did not return an evaluation trace")
    api_recommendation_items = api_recommendations.get("recommendations")
    if not isinstance(api_recommendation_items, list) or not isinstance(
        api_recommendation_items[0], dict
    ):
        fail("API recommendations returned malformed recommendations")
    api_explanation = require_recommendation_explanation(
        api_recommendation_items[0], "API recommendation"
    )
    checks.append(
        Check(
            "api_recommendations",
            f"count={api_recommendation_count} trace={trace_event_id}",
        )
    )
    checks.append(
        Check(
            "recommendation_explanation",
            f"signals={len(api_explanation['matched_intent'])}",
        )
    )

    web_recommendations = post_json(
        f"{web_url}/api/recommendations",
        recommendation_payload,
    )
    web_recommendation_count = web_recommendations.get("count")
    if not isinstance(web_recommendation_count, int) or web_recommendation_count < 1:
        fail("web recommendation proxy returned malformed count")
    web_trace_event_id = web_recommendations.get("trace_event_id")
    if not isinstance(web_trace_event_id, int):
        fail("web recommendation proxy did not return a trace_event_id")
    web_recommendation_items = web_recommendations.get("recommendations")
    if not isinstance(web_recommendation_items, list) or not isinstance(
        web_recommendation_items[0], dict
    ):
        fail("web recommendation proxy returned malformed recommendations")
    web_explanation = require_recommendation_explanation(
        web_recommendation_items[0], "web recommendation proxy"
    )
    checks.append(
        Check(
            "web_recommendation_proxy",
            f"count={web_recommendation_count} trace={web_trace_event_id}",
        )
    )
    checks.append(
        Check(
            "web_recommendation_explanation_proxy",
            f"signals={len(web_explanation['matched_intent'])}",
        )
    )
    first_recommendation = api_recommendation_items[0]
    recommended_offer_id = first_recommendation.get("offer_id")
    if not isinstance(recommended_offer_id, int):
        fail("API recommendation is missing offer_id")
    feedback = post_json(
        f"{api_url}/recommendations/feedback",
        {
            "trace_event_id": trace_event_id,
            "offer_id": recommended_offer_id,
            "rating": "helpful",
            "source": "staging_smoke",
        },
        expected_status=201,
    )
    if feedback.get("rating") != "helpful":
        fail("recommendation feedback response did not echo helpful rating")
    checks.append(Check("recommendation_feedback", f"offer_id={recommended_offer_id}"))

    web_feedback = post_json(
        f"{web_url}/api/recommendation-feedback",
        {
            "trace_event_id": web_trace_event_id,
            "offer_id": recommended_offer_id,
            "rating": "not_helpful",
            "source": "staging_smoke",
        },
        expected_status=201,
    )
    if web_feedback.get("rating") != "not_helpful":
        fail("web recommendation feedback proxy did not echo not_helpful rating")
    checks.append(
        Check("web_recommendation_feedback_proxy", f"offer_id={recommended_offer_id}")
    )

    click = post_json(
        f"{api_url}/clicks",
        {"offer_id": offer_id, "target_type": "product", "referrer": "staging-smoke"},
        expected_status=201,
    )
    if click.get("offer_id") != offer_id:
        fail("click tracking response did not echo the tracked offer")
    checks.append(Check("click_tracking", f"offer_id={offer_id}"))

    web_click = post_json(
        f"{web_url}/api/clicks",
        {"offer_id": offer_id, "target_type": "affiliate", "referrer": "staging-smoke"},
        expected_status=201,
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

    traces = get_json(f"{api_url}/admin/affiliate/recommendation-traces", token)
    if (
        not isinstance(traces.get("total_traces"), int)
        or traces["total_traces"] < 2
        or not isinstance(traces.get("recent_traces"), list)
    ):
        fail("recommendation trace admin endpoint returned malformed data")
    recent_trace_ids = [
        trace.get("id") for trace in traces["recent_traces"] if isinstance(trace, dict)
    ]
    if trace_event_id not in recent_trace_ids:
        fail("recommendation trace admin endpoint did not include the API trace")
    checks.append(Check("recommendation_traces", f"total={traces['total_traces']}"))

    web_traces = post_json(
        f"{web_url}/api/admin/recommendation-traces", {"adminToken": token}
    )
    if not isinstance(web_traces.get("total_traces"), int):
        fail("web recommendation trace proxy returned malformed data")
    checks.append(
        Check("web_recommendation_trace_proxy", f"total={web_traces['total_traces']}")
    )

    evaluation = get_json(f"{api_url}/admin/affiliate/recommendation-evaluation", token)
    if (
        evaluation.get("status") != "ok"
        or evaluation.get("failed_count") != 0
        or evaluation.get("passed_count", 0) < 1
    ):
        fail(f"recommendation evaluation failed: {evaluation}")
    checks.append(
        Check(
            "recommendation_evaluation",
            f"passed={evaluation['passed_count']} failed={evaluation['failed_count']}",
        )
    )

    web_evaluation = post_json(
        f"{web_url}/api/admin/recommendation-evaluation", {"adminToken": token}
    )
    if web_evaluation.get("status") != "ok":
        fail("web recommendation evaluation proxy returned a failing summary")
    checks.append(
        Check(
            "web_recommendation_evaluation_proxy",
            f"passed={web_evaluation['passed_count']}",
        )
    )

    feedback_summary = get_json(
        f"{api_url}/admin/affiliate/recommendation-feedback", token
    )
    if (
        not isinstance(feedback_summary.get("total_feedback"), int)
        or feedback_summary["total_feedback"] < 2
        or not isinstance(feedback_summary.get("helpful_count"), int)
        or not isinstance(feedback_summary.get("not_helpful_count"), int)
    ):
        fail("recommendation feedback admin endpoint returned malformed data")
    checks.append(
        Check(
            "recommendation_feedback_summary",
            (
                f"helpful={feedback_summary['helpful_count']} "
                f"not_helpful={feedback_summary['not_helpful_count']}"
            ),
        )
    )

    web_feedback_summary = post_json(
        f"{web_url}/api/admin/recommendation-feedback", {"adminToken": token}
    )
    if not isinstance(web_feedback_summary.get("total_feedback"), int):
        fail("web recommendation feedback proxy returned malformed data")
    checks.append(
        Check(
            "web_recommendation_feedback_summary_proxy",
            f"total={web_feedback_summary['total_feedback']}",
        )
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
