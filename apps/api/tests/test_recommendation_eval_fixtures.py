from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
EVALUATOR_PATH = ROOT / "scripts" / "evaluate_recommendations.py"


def load_evaluator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("evaluate_recommendations", EVALUATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recommendation_eval_fixtures_pass() -> None:
    evaluator = load_evaluator()
    cases = evaluator.load_cases(evaluator.FIXTURE_PATH)

    results = [evaluator.run_case(case) for case in cases]

    assert len(results) == 4
    assert all("=pass " in result for result in results)
