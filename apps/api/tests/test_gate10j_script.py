"""Unit tests for Gate 10J staging auto-tune scaffold (no live HTTP)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "gate10j_auto_tune.py"

STAGING_SNIPPET = """\
      - key: BANDIT_POLICY
        value: linucb
      - key: FEATURE_NEURAL_BANDIT
        value: "false"
      - key: FEATURE_RLHF_ROUTER
        value: "false"
      - key: FEATURE_AUTO_TUNING
        value: "false"
      - key: FEATURE_KILL_SWITCH
        value: "true"
      - key: AUTO_TUNE_DRY_RUN
        value: "true"
"""


def load_gate10j() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gate10j_auto_tune", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_apply_staging_blueprint_dry_run_does_not_write(tmp_path: Path) -> None:
    g = load_gate10j()
    path = tmp_path / "render.yaml"
    path.write_text(STAGING_SNIPPET, encoding="utf-8")
    result = g.apply_staging_autotune_blueprint(path, enabled=True, dry_run=True)
    assert result["dry_run"] is True
    assert result["after"]["FEATURE_AUTO_TUNING"] == "true"
    assert result["after"]["AUTO_TUNE_DRY_RUN"] == "true"
    assert result["after"]["FEATURE_NEURAL_BANDIT"] == "false"
    assert result["after"]["FEATURE_RLHF_ROUTER"] == "false"
    assert result["after"]["BANDIT_POLICY"] == "linucb"
    assert path.read_text(encoding="utf-8") == STAGING_SNIPPET


def test_apply_staging_blueprint_write_and_cleanup(tmp_path: Path) -> None:
    g = load_gate10j()
    path = tmp_path / "render.yaml"
    path.write_text(STAGING_SNIPPET, encoding="utf-8")
    enabled = g.apply_staging_autotune_blueprint(path, enabled=True, dry_run=False)
    assert enabled["after"]["FEATURE_AUTO_TUNING"] == "true"
    text = path.read_text(encoding="utf-8")
    assert 'FEATURE_AUTO_TUNING\n        value: "true"' in text
    assert "value: linucb" in text
    cleaned = g.apply_staging_autotune_blueprint(path, enabled=False, dry_run=False)
    assert cleaned["after"]["FEATURE_AUTO_TUNING"] == "false"
    assert cleaned["after"]["AUTO_TUNE_DRY_RUN"] == "true"
    assert cleaned["after"]["BANDIT_POLICY"] == "linucb"


def test_refuses_production_blueprint_filename(tmp_path: Path) -> None:
    g = load_gate10j()
    path = tmp_path / "render-production.yaml"
    path.write_text(STAGING_SNIPPET, encoding="utf-8")
    with pytest.raises(g.Gate10JError, match="production Blueprint"):
        g.apply_staging_autotune_blueprint(path, enabled=True, dry_run=True)
    assert path.read_text(encoding="utf-8") == STAGING_SNIPPET


def test_classify_audit_propose_vs_apply() -> None:
    g = load_gate10j()
    classified = g.classify_audit_events(
        [
            {"event": "autotune_propose", "payload": {"applied": False}},
            {"event": "config_update"},
            {"event": "hparams_update", "payload": {"reason": "autotune"}},
        ]
    )
    assert len(classified["proposed"]) == 1
    assert len(classified["applied"]) == 1
    assert classified["applied"][0]["event"] == "hparams_update"
