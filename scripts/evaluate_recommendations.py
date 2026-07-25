#!/usr/bin/env python3
"""Run deterministic Gate 4B recommendation evaluation fixtures."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
FIXTURE_PATH = API_ROOT / "tests" / "fixtures" / "recommendation_eval_cases.json"
sys.path.insert(0, str(API_ROOT))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models import Offer  # noqa: E402
from app.services.affiliate.ingestion import AffiliateIngestionService  # noqa: E402
from app.services.affiliate.mock_provider import MockAffiliateProvider  # noqa: E402
from app.services.click_tracking import ClickTrackingInput, record_click  # noqa: E402
from app.services.recommendations import recommend_offers  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


def fail(message: str) -> None:
    print(f"recommendation_eval=error: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_cases(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        fail(f"could not read fixture file {path}: {exc}")
    except json.JSONDecodeError as exc:
        fail(f"fixture file is invalid JSON: {exc}")

    if not isinstance(data, list) or not data:
        fail("fixture file must contain at least one case")
    for case in data:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            fail("each fixture case must be an object with an id")
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
    offer_id = db.scalar(
        select(Offer.id).where(Offer.source_record_id == source_record_id)
    )
    if offer_id is None:
        fail(f"fixture references unknown source_record_id {source_record_id!r}")
    return offer_id


def apply_pre_clicks(db: Session, case: dict[str, Any]) -> None:
    clicks = case.get("pre_clicks", [])
    if not isinstance(clicks, list):
        fail(f"{case['id']} pre_clicks must be a list")

    for click in clicks:
        if not isinstance(click, dict):
            fail(f"{case['id']} pre_click entry must be an object")
        source_record_id = click.get("source_record_id")
        target_type = click.get("target_type")
        if not isinstance(source_record_id, str) or not isinstance(target_type, str):
            fail(
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
            fail(f"{case['id']} could not record pre_click for {source_record_id}")


def assert_equal(case_id: str, field: str, actual: object, expected: object) -> None:
    if actual != expected:
        fail(f"{case_id} expected {field}={expected!r}, got {actual!r}")


def assert_trace(case_id: str, trace: object, expected: dict[str, Any]) -> None:
    if not isinstance(trace, list):
        fail(f"{case_id} trace is not a list")
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
        fail(f"{case_id} trace missing notes: {', '.join(sorted(missing_notes))}")


def run_case(case: dict[str, Any]) -> str:
    case_id = case["id"]
    expected = case.get("expected")
    if not isinstance(expected, dict):
        fail(f"{case_id} expected must be an object")

    db = make_session()
    try:
        asyncio.run(seed_mock_data(db))
        apply_pre_clicks(db, case)

        intent = case.get("intent")
        limit = case.get("limit", 5)
        if not isinstance(intent, str) or not isinstance(limit, int):
            fail(f"{case_id} intent must be a string and limit must be an integer")

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
        assert_equal(
            case_id, "has_coupon", parsed_intent.has_coupon, expected["has_coupon"]
        )
        assert_equal(
            case_id,
            "has_cashback",
            parsed_intent.has_cashback,
            expected["has_cashback"],
        )
        assert_equal(
            case_id, "freshness", parsed_intent.freshness, expected["freshness"]
        )

        min_count = expected.get("min_count")
        if not isinstance(min_count, int) or len(recommendations) < min_count:
            fail(f"{case_id} expected at least {min_count} recommendations")

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
        assert_equal(
            case_id, "first_merchant", first["merchant"], expected["first_merchant"]
        )

        first_min_click_count = expected.get("first_min_click_count")
        if (
            isinstance(first_min_click_count, int)
            and first["click_count"] < first_min_click_count
        ):
            fail(
                f"{case_id} expected first click_count >= {first_min_click_count}, "
                f"got {first['click_count']}"
            )

        assert_trace(case_id, result["trace"], expected)
        return f"{case_id}=pass count={len(recommendations)} first={source_record_id}"
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_cases(args.fixtures)
    results = [run_case(case) for case in cases]

    print("recommendation_eval=ok")
    print(f"cases={len(results)}")
    for result in results:
        print(result)


if __name__ == "__main__":
    main()
