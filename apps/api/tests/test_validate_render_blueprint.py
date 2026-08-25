"""Unit tests for Gate 10J's --allow-auto-tuning support in the Blueprint validator."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "validate_render_blueprint.py"

PROD_ALLOW_BASE = [
    "--profile",
    "production",
    "--allow-neural-bandit",
    "--allow-rlhf-router",
    "--allow-rlhf-after-neural",
]


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_render_blueprint", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _production_blueprint(tmp_path: Path, *, auto_tuning: str, dry_run: str) -> Path:
    real = yaml.safe_load((ROOT / "render-production.yaml").read_text(encoding="utf-8"))
    env_vars = real["services"][0]["envVars"]
    for entry in env_vars:
        if entry["key"] == "FEATURE_AUTO_TUNING":
            entry["value"] = auto_tuning
        if entry["key"] == "AUTO_TUNE_DRY_RUN":
            entry["value"] = dry_run
    path = tmp_path / "render-production.yaml"
    path.write_text(yaml.safe_dump(real, sort_keys=False), encoding="utf-8")
    return path


def _run(blueprint: Path, extra_args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(blueprint), *PROD_ALLOW_BASE, *extra_args],
        capture_output=True,
        text=True,
    )


def test_auto_tuning_true_without_allow_flag_fails(tmp_path: Path) -> None:
    bp = _production_blueprint(tmp_path, auto_tuning="true", dry_run="true")
    result = _run(bp, [])
    assert result.returncode != 0
    assert "FEATURE_AUTO_TUNING must be false" in result.stderr


def test_auto_tuning_requires_kill_switch_allow(tmp_path: Path) -> None:
    bp = _production_blueprint(tmp_path, auto_tuning="true", dry_run="true")
    result = _run(bp, ["--allow-auto-tuning"])
    assert result.returncode != 0
    assert "FEATURE_KILL_SWITCH" in result.stderr


def test_auto_tuning_requires_dry_run_true(tmp_path: Path) -> None:
    bp = _production_blueprint(tmp_path, auto_tuning="true", dry_run="false")
    result = _run(bp, ["--allow-kill-switch", "--allow-auto-tuning"])
    assert result.returncode != 0
    assert "AUTO_TUNE_DRY_RUN=true" in result.stderr


def test_auto_tuning_true_with_full_allow_flags_passes(tmp_path: Path) -> None:
    bp = _production_blueprint(tmp_path, auto_tuning="true", dry_run="true")
    result = _run(bp, ["--allow-kill-switch", "--allow-auto-tuning"])
    assert result.returncode == 0
    assert "production_provisioning_validation=ok" in result.stdout


def test_auto_tuning_false_still_passes_without_new_flag(tmp_path: Path) -> None:
    bp = _production_blueprint(tmp_path, auto_tuning="false", dry_run="true")
    result = _run(bp, ["--allow-kill-switch"])
    assert result.returncode == 0


def test_validate_env_helper_enforces_coupling_directly(tmp_path: Path) -> None:
    """Exercise validate_env() directly (not just the CLI) for the new coupling rule."""
    validator = load_validator()
    bp_path = _production_blueprint(tmp_path, auto_tuning="true", dry_run="true")
    raw, data = validator.load_blueprint(bp_path, profile="production")
    services = validator.service_by_name(data, profile="production")
    with pytest.raises(SystemExit):
        validator.validate_env(
            services,
            profile="production",
            allow_neural_bandit=True,
            allow_rlhf_router=True,
            allow_rlhf_after_neural=True,
            allow_auto_tuning=True,
            allow_kill_switch=False,
        )
