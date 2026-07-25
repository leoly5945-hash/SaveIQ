from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models import Offer
from app.services.affiliate.ingestion import AffiliateIngestionService
from app.services.affiliate.mock_provider import MockAffiliateProvider
from app.services.click_tracking import ClickTrackingInput, record_click
from app.services.recommendations import recommend_offers

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "recommendation_eval_cases.json"
)


class EvaluationFailure(ValueError):
    pass


class EvaluationCaseResult(TypedDict):
    id: str
    status: str
    intent: str
    count: int
    first_source_record_id: str | None
    first_merchant: str | None
    trace_steps: list[str]
    required_trace_steps: list[str]
    failure: str | None


class EvaluationSummary(TypedDict):
    status: str
    strategy: str
    case_count: int
    passed_count: int
    failed_count: int
    cases: list[EvaluationCaseResult]


@dataclass(frozen=True)
class _CaseRun:
    count: int
    first_source_record_id: str | None
    first_merchant: str | None
    trace_steps: list[str]


def load_cases(path: Path = DEFAULT_FIXTURE_PATH) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvaluationFailure(f"could not read fixture file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationFailure(f"fixture file is invalid JSON: {exc}") from exc

    if not isinstance(data, list) or not data:
        raise EvaluationFailure("fixture file must contain at least one case")
    for case in data:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise EvaluationFailure("each fixture case must be an object with an id")
    return data


def make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


async def seed_mock_data(db: Session) -> None:
    await AffiliateIngestionService(db, MockAffiliateProvider()).run_sync()


def source_record_to_offer_id(db: Session, source_record_id: str) -> int:
    offer_id = db.scalar(select(Offer.id).where(Offer.source_record_id == source_record_id))
    if offer_id is None:
        raise EvaluationFailure(f"fixture references unknown source_record_id {source_record_id!r}")
    return offer_id


def apply_pre_clicks(db: Session, case: dict[str, Any]) -> None:
    clicks = case.get("pre_clicks", [])
    if not isinstance(clicks, list):
        raise EvaluationFailure(f"{case['id']} pre_clicks must be a list")

    for click in clicks:
        if not isinstance(click, dict):
            raise EvaluationFailure(f"{case['id']} pre_click entry must be an object")
        source_record_id = click.get("source_record_id")
        target_type = click.get("target_type")
        if not isinstance(source_record_id, str) or not isinstance(target_type, str):
            raise EvaluationFailure(
                f"{case['id']} pre_click entry is missing source_record_id or target_type"
            )
        offer_id = source_record_to_offer_id(db, source_record_id)
        result = record_click(
            db,
            ClickTrackingInput(
                offer_id=offer_id,
                target_type=target_type,
                referrer=f"recommendation-eval:{case['id']}",
            ),
        )
        if result is None:
            raise EvaluationFailure(
                f"{case['id']} could not record pre_click for {source_record_id}"
            )


def assert_equal(case_id: str, field: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise EvaluationFailure(f"{case_id} expected {field}={expected!r}, got {actual!r}")


def assert_trace(case_id: str, trace: object, expected: dict[str, Any]) -> list[str]:
    if not isinstance(trace, list):
        raise EvaluationFailure(f"{case_id} trace is not a list")
    steps = [step.get("step") for step in trace if isinstance(step, dict)]
    assert_equal(case_id, "trace steps", steps, expected["required_trace_steps"])

    trace_notes = {
        note
        for step in trace
        if isinstance(step, dict)
        for note in step.get("notes", [])
        if isinstance(note, str)
    }
    missing_notes = set(expected["required_trace_notes"]) - trace_notes
    if missing_notes:
        raise EvaluationFailure(
            f"{case_id} trace missing notes: {', '.join(sorted(missing_notes))}"
        )
    return [str(step) for step in steps]


def evaluate_case(case: dict[str, Any]) -> _CaseRun:
    case_id = case["id"]
    expected = case.get("expected")
    if not isinstance(expected, dict):
        raise EvaluationFailure(f"{case_id} expected must be an object")

    db = make_session()
    try:
        asyncio.run(seed_mock_data(db))
        apply_pre_clicks(db, case)

        intent = case.get("intent")
        limit = case.get("limit", 5)
        if not isinstance(intent, str) or not isinstance(limit, int):
            raise EvaluationFailure(
                f"{case_id} intent must be a string and limit must be an integer"
            )

        result = recommend_offers(db, intent, limit)
        parsed_intent = result["intent"]
        recommendations = result["results"]

        assert_equal(case_id, "strategy", result["strategy"], expected["strategy"])
        assert_equal(
            case_id,
            "search_query",
            parsed_intent.search_query,
            expected["search_query"],
        )
        assert_equal(case_id, "sort", parsed_intent.sort, expected["sort"])
        assert_equal(case_id, "has_coupon", parsed_intent.has_coupon, expected["has_coupon"])
        assert_equal(
            case_id,
            "has_cashback",
            parsed_intent.has_cashback,
            expected["has_cashback"],
        )
        assert_equal(case_id, "freshness", parsed_intent.freshness, expected["freshness"])

        min_count = expected.get("min_count")
        if not isinstance(min_count, int) or len(recommendations) < min_count:
            raise EvaluationFailure(f"{case_id} expected at least {min_count} recommendations")

        first = recommendations[0]
        source_record_id = db.scalar(
            select(Offer.source_record_id).where(Offer.id == first["offer_id"])
        )
        assert_equal(
            case_id,
            "first_source_record_id",
            source_record_id,
            expected["first_source_record_id"],
        )
        assert_equal(case_id, "first_merchant", first["merchant"], expected["first_merchant"])

        first_min_click_count = expected.get("first_min_click_count")
        if isinstance(first_min_click_count, int) and first["click_count"] < first_min_click_count:
            raise EvaluationFailure(
                f"{case_id} expected first click_count >= {first_min_click_count}, "
                f"got {first['click_count']}"
            )

        trace_steps = assert_trace(case_id, result["trace"], expected)
        return _CaseRun(
            count=len(recommendations),
            first_source_record_id=source_record_id,
            first_merchant=first["merchant"],
            trace_steps=trace_steps,
        )
    finally:
        db.close()


def evaluate_recommendation_fixtures(
    path: Path = DEFAULT_FIXTURE_PATH,
) -> EvaluationSummary:
    cases = load_cases(path)
    results: list[EvaluationCaseResult] = []

    for case in cases:
        expected = case.get("expected", {})
        required_trace_steps = (
            expected.get("required_trace_steps", []) if isinstance(expected, dict) else []
        )
        try:
            run = evaluate_case(case)
            results.append(
                {
                    "id": case["id"],
                    "status": "pass",
                    "intent": str(case.get("intent", "")),
                    "count": run.count,
                    "first_source_record_id": run.first_source_record_id,
                    "first_merchant": run.first_merchant,
                    "trace_steps": run.trace_steps,
                    "required_trace_steps": [str(step) for step in required_trace_steps],
                    "failure": None,
                }
            )
        except EvaluationFailure as exc:
            results.append(
                {
                    "id": case["id"],
                    "status": "fail",
                    "intent": str(case.get("intent", "")),
                    "count": 0,
                    "first_source_record_id": None,
                    "first_merchant": None,
                    "trace_steps": [],
                    "required_trace_steps": [str(step) for step in required_trace_steps],
                    "failure": str(exc),
                }
            )

    passed_count = sum(1 for result in results if result["status"] == "pass")
    failed_count = len(results) - passed_count
    return {
        "status": "ok" if failed_count == 0 else "failed",
        "strategy": "rule_based_mock_v0",
        "case_count": len(results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "cases": results,
    }
