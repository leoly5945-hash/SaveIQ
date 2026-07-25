#!/usr/bin/env python3
"""Run deterministic Gate 4B recommendation evaluation fixtures."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
FIXTURE_PATH = API_ROOT / "tests" / "fixtures" / "recommendation_eval_cases.json"
sys.path.insert(0, str(API_ROOT))

from app.services.recommendation_evaluation import (  # noqa: E402
    EvaluationFailure,
    evaluate_case,
    evaluate_recommendation_fixtures,
    load_cases as _load_cases,
)


def fail(message: str) -> None:
    print(f"recommendation_eval=error: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_PATH)
    return parser.parse_args()


def run_case(case: dict[str, object]) -> str:
    result = evaluate_case(case)
    return (
        f"{case['id']}=pass count={result.count} "
        f"first={result.first_source_record_id}"
    )


def load_cases(path: Path) -> list[dict[str, object]]:
    return _load_cases(path)


def main() -> None:
    args = parse_args()
    try:
        summary = evaluate_recommendation_fixtures(args.fixtures)
    except EvaluationFailure as exc:
        fail(str(exc))

    print("recommendation_eval=ok" if summary["status"] == "ok" else "recommendation_eval=failed")
    print(f"cases={summary['case_count']}")
    for result in summary["cases"]:
        if result["status"] == "pass":
            print(
                f"{result['id']}=pass count={result['count']} "
                f"first={result['first_source_record_id']}"
            )
        else:
            print(f"{result['id']}=fail reason={result['failure']}")

    if summary["failed_count"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
