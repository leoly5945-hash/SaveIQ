#!/usr/bin/env python3
"""Automate Gate 10D production rollout: verify → deploy → smoke → A/B → decide.

Safety:
- Never modifies canary config.
- Starts A/B only after smoke passes with FEATURE_ABTEST off.
- Stops A/B (rollback) on hard failures or negative decision.
- Secrets only from environment (ADMIN_API_TOKEN, optional RENDER_API_KEY).

Usage examples:

  # Local verify + wait for operator deploy, then run online phases
  ADMIN_API_TOKEN=... PYTHON=.venv/bin/python scripts/gate10d_abtest_rollout.py \\
    --skip-merge --skip-publish --skip-pin --skip-deploy

  # Full online experiment after image is live
  ADMIN_API_TOKEN=... PYTHON=.venv/bin/python scripts/gate10d_abtest_rollout.py \\
    --from-smoke
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_API_URL = "https://dealhunter-production-api.onrender.com"
DEFAULT_WEB_URL = "https://dealhunter-production-web.onrender.com"
USER_AGENT = "SaveIQ-Gate10D-Rollout/1.0"
EXPERIMENT = "router_holdout_v1"


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


class RolloutError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def run(
    cmd: list[str], *, cwd: str | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(
            result.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )
    if check and result.returncode != 0:
        raise RolloutError(f"command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def http_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    body: dict[str, Any] | None = None,
    render_key: str | None = None,
    expected: int | None = 200,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Admin-Token"] = token
    if render_key:
        headers["Authorization"] = f"Bearer {render_key}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        status = exc.code
        if expected is not None and status != expected:
            raise RolloutError(f"{method} {url} -> HTTP {status}: {payload}") from exc
        if expected is None:
            data_obj = json.loads(payload) if payload else {}
            if not isinstance(data_obj, dict):
                return {"_status": status, "_raw": payload}
            data_obj["_status"] = status
            return data_obj
        data_obj = json.loads(payload) if payload else {}
        if not isinstance(data_obj, dict):
            raise RolloutError(f"{url} non-object JSON") from exc
        return data_obj
    except Exception as exc:  # noqa: BLE001
        raise RolloutError(f"{method} {url} failed: {exc}") from exc

    if expected is not None and status != expected:
        raise RolloutError(f"{method} {url} -> HTTP {status}: {payload}")
    if not payload:
        return {}
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise RolloutError(f"{url} did not return a JSON object")
    return parsed


def http_text(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def require_admin_token() -> str:
    token = os.environ.get("ADMIN_API_TOKEN", "").strip()
    if not token:
        raise RolloutError(
            "ADMIN_API_TOKEN is required (export from Render production env)"
        )
    return token


def snapshot_canary(api_url: str, token: str) -> dict[str, Any]:
    status = http_json(f"{api_url}/admin/canary/status", token=token)
    log(
        "canary_snapshot="
        f"enabled={status.get('enabled')} percentage={status.get('percentage')} "
        f"(will not modify)"
    )
    return status


def assert_abtest_off(api_url: str, token: str) -> None:
    status = http_json(f"{api_url}/admin/abtest/status", token=token)
    if status.get("feature_enabled") is True or status.get("running") is True:
        raise RolloutError(
            "A/B must be off before smoke/enable gate "
            f"(feature_enabled={status.get('feature_enabled')} running={status.get('running')})"
        )


def stop_abtest(api_url: str, token: str) -> None:
    log("==> A/B rollback: POST /admin/abtest/stop")
    try:
        stopped = http_json(
            f"{api_url}/admin/abtest/stop", method="POST", token=token, body={}
        )
        log(f"abtest_stopped={json.dumps(stopped, sort_keys=True)}")
    except Exception as exc:  # noqa: BLE001
        log(f"abtest_rollback_error={exc}")


def wait_for_abtest_route(api_url: str, *, timeout_s: int = 600) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            request = urllib.request.Request(
                f"{api_url}/admin/abtest/status",
                headers={"User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                # Auth required => route exists.
                if response.status in {200, 401, 403}:
                    log(f"abtest_route_ready status={response.status}")
                    return
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                log(f"abtest_route_ready status={exc.code}")
                return
            if exc.code != 404:
                log(f"abtest_route_probe status={exc.code}")
        except Exception as exc:  # noqa: BLE001
            log(f"abtest_route_probe_error={exc}")
        time.sleep(10)
    raise RolloutError("timed out waiting for /admin/abtest/status on production")


def generate_traffic(
    api_url: str, *, users: int, requests_per_user: int
) -> dict[str, int]:
    groups: dict[str, int] = {}
    for i in range(users):
        user_id = f"abtest_rollout_{i:04d}"
        for _ in range(requests_per_user):
            body = {
                "intent": "best laptop deals under 1000",
                "limit": 3,
                "market": "CA",
            }
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "X-User-ID": user_id,
                "X-Anonymous-User-Id": user_id,
            }
            request = urllib.request.Request(
                f"{api_url}/recommendations",
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    group = response.headers.get("X-AB-Group", "none")
                    groups[group] = groups.get(group, 0) + 1
            except urllib.error.HTTPError as exc:
                groups["http_error"] = groups.get("http_error", 0) + 1
                log(f"traffic_error user={user_id} status={exc.code}")
            except Exception as exc:  # noqa: BLE001
                groups["transport_error"] = groups.get("transport_error", 0) + 1
                log(f"traffic_error user={user_id} err={exc}")
    return groups


def metrics_snapshot(api_url: str) -> dict[str, int]:
    body = http_text(f"{api_url}/metrics")
    counts = {
        "ab_control_lines": body.count('ab_group="control"'),
        "ab_treatment_lines": body.count('ab_group="treatment_a"'),
        "ab_none_lines": body.count('ab_group="none"'),
        "canary_true_lines": body.count('canary="true"'),
        "canary_false_lines": body.count('canary="false"'),
    }
    return counts


def decide(stats: dict[str, Any], significance: dict[str, Any]) -> tuple[str, str]:
    """Return (decision, reason). Decisions: continue_hold | promote_review | stop_rollback."""
    groups = stats.get("groups") or {}
    control = groups.get("control") or {}
    treatment = groups.get("treatment_a") or {}
    c_exp = int(control.get("exposures") or 0)
    t_exp = int(treatment.get("exposures") or 0)
    if c_exp < 20 or t_exp < 20:
        return (
            "continue_hold",
            f"insufficient exposures control={c_exp} treatment={t_exp}",
        )

    c_rate = float(control.get("conversion_rate") or 0.0)
    t_rate = float(treatment.get("conversion_rate") or 0.0)
    c_conv = int(control.get("conversions") or 0)
    t_conv = int(treatment.get("conversions") or 0)

    # Exposure-only probes (no conversion events) cannot run chi2 — treat as hold
    # if assignment looks roughly balanced.
    if significance.get("error") or (c_conv + t_conv) == 0:
        total = c_exp + t_exp
        share = abs(c_exp - t_exp) / max(total, 1)
        if share > 0.35:
            return (
                "stop_rollback",
                f"skewed assignment control={c_exp} treatment={t_exp}",
            )
        return (
            "continue_hold",
            (
                f"assignment ok control={c_exp} treatment={t_exp}; "
                f"no conversion events yet ({significance.get('error') or 'conversions=0'})"
            ),
        )

    p_value = significance.get("p_value")
    significant = bool(significance.get("significant"))

    # Guardrail: if treatment conversion much worse when data exists, stop.
    if significant and t_rate + 0.05 < c_rate:
        return "stop_rollback", f"treatment worse (p={p_value}, c={c_rate}, t={t_rate})"
    if significant and t_rate > c_rate + 0.05:
        return (
            "promote_review",
            f"treatment better (p={p_value}, c={c_rate}, t={t_rate})",
        )
    return "continue_hold", f"no clear lift yet (p={p_value}, c={c_rate}, t={t_rate})"


def find_publish_digests(repo_root: str, sha: str) -> tuple[str, str]:
    """Best-effort: read latest successful Publish Containers run for sha."""
    result = run(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            "Publish Containers",
            "--commit",
            sha,
            "--json",
            "databaseId,conclusion",
            "--limit",
            "5",
        ],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise RolloutError("failed to list publish runs")
    runs = json.loads(result.stdout or "[]")
    run_id = None
    for item in runs:
        if item.get("conclusion") == "success":
            run_id = item["databaseId"]
            break
    if run_id is None:
        raise RolloutError(f"no successful Publish Containers run for {sha}")

    log_result = run(
        ["gh", "run", "view", str(run_id), "--log"], cwd=repo_root, check=False
    )
    engine = None
    web = None
    for line in (log_result.stdout or "").splitlines():
        if "saveiq-engine=ghcr.io/" in line and "sha256:" in line:
            engine = line.split("saveiq-engine=", 1)[1].strip()
        if "saveiq-web=ghcr.io/" in line and "sha256:" in line:
            web = line.split("saveiq-web=", 1)[1].strip()
    if not engine or not web:
        # Fallback parse push lines
        for line in (log_result.stdout or "").splitlines():
            if "saveiq-engine:" in line and "@sha256:" in line:
                part = line.split("@sha256:")[-1]
                digest = part.split()[0].strip()
                engine = f"ghcr.io/leoly5945-hash/saveiq-engine@sha256:{digest}"
            if "saveiq-web:" in line and "@sha256:" in line:
                part = line.split("@sha256:")[-1]
                digest = part.split()[0].strip()
                web = f"ghcr.io/leoly5945-hash/saveiq-web@sha256:{digest}"
    if not engine or not web:
        raise RolloutError("could not parse digests from publish logs")
    return engine, web


def pin_blueprint(repo_root: str, engine_ref: str, web_ref: str) -> None:
    path = os.path.join(repo_root, "render-production.yaml")
    text = open(path, encoding="utf-8").read()
    import re

    engine_digest = engine_ref.split("@", 1)[-1] if "@" in engine_ref else engine_ref
    web_digest = web_ref.split("@", 1)[-1] if "@" in web_ref else web_ref
    if not engine_digest.startswith("sha256:"):
        raise RolloutError(f"bad engine digest: {engine_ref}")
    if not web_digest.startswith("sha256:"):
        raise RolloutError(f"bad web digest: {web_ref}")
    text2, n1 = re.subn(
        r'(url: "ghcr\.io/leoly5945-hash/saveiq-engine@)sha256:[a-f0-9]{64}(")',
        rf"\g<1>{engine_digest}\2",
        text,
        count=1,
    )
    text3, n2 = re.subn(
        r'(url: "ghcr\.io/leoly5945-hash/saveiq-web@)sha256:[a-f0-9]{64}(")',
        rf"\g<1>{web_digest}\2",
        text2,
        count=1,
    )
    if n1 != 1 or n2 != 1:
        raise RolloutError(f"digest pin replace failed engine={n1} web={n2}")
    open(path, "w", encoding="utf-8").write(text3)
    log(f"pinned_api=saveiq-engine@{engine_digest}")
    log(f"pinned_web=saveiq-web@{web_digest}")


def render_trigger_deploy(service_id: str, image_url: str, api_key: str) -> None:
    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    result = http_json(
        url,
        method="POST",
        render_key=api_key,
        body={"imageUrl": image_url},
        expected=None,
    )
    status = int(result.get("_status") or 0)
    if status not in {200, 201, 202}:
        raise RolloutError(f"render deploy failed status={status} body={result}")


def maybe_deploy_via_render_api(engine_ref: str, web_ref: str) -> bool:
    api_key = os.environ.get("RENDER_API_KEY", "").strip()
    api_svc = os.environ.get("RENDER_SERVICE_ID_API", "").strip()
    web_svc = os.environ.get("RENDER_SERVICE_ID_WEB", "").strip()
    if not api_key:
        log(
            "deploy=manual (RENDER_API_KEY missing) — Sync Blueprint saveiq-production in dashboard"
        )
        return False
    if not api_svc or not web_svc:
        log(
            "deploy=manual (set RENDER_SERVICE_ID_API and RENDER_SERVICE_ID_WEB "
            "to trigger API deploys)"
        )
        return False
    log("==> Triggering Render API deploys")
    render_trigger_deploy(api_svc, engine_ref, api_key)
    render_trigger_deploy(web_svc, web_ref, api_key)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate 10D A/B production rollout automation"
    )
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_API_URL))
    parser.add_argument("--web-url", default=os.environ.get("WEB_URL", DEFAULT_WEB_URL))
    parser.add_argument(
        "--repo-root",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    )
    parser.add_argument("--pr", type=int, default=12, help="Gate 10D PR number")
    parser.add_argument(
        "--from-smoke", action="store_true", help="Skip git/publish/pin/deploy phases"
    )
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument("--skip-publish-wait", action="store_true")
    parser.add_argument("--skip-pin", action="store_true")
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--skip-traffic", action="store_true")
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Do not auto-stop A/B after decision",
    )
    parser.add_argument("--users", type=int, default=40)
    parser.add_argument("--requests-per-user", type=int, default=2)
    parser.add_argument(
        "--local-verify", action="store_true", help="Run ruff/mypy/pytest before merge"
    )
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    web_url = args.web_url.rstrip("/")
    root = args.repo_root
    python = os.environ.get("PYTHON", os.path.join(root, ".venv/bin/python"))
    steps: list[StepResult] = []

    try:
        if args.local_verify:
            log("==> Local verify")
            run(
                [
                    python,
                    "-m",
                    "ruff",
                    "check",
                    "apps/api/app",
                    "apps/api/tests",
                    "scripts",
                ],
                cwd=root,
            )
            run([python, "-m", "mypy", "apps/api/app"], cwd=root)
            run([python, "-m", "pytest", "apps/api/tests", "-q"], cwd=root)
            steps.append(StepResult("local_verify", True, "ok"))

        if not args.from_smoke and not args.skip_merge:
            log("==> Ensure PR merged")
            pr = run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(args.pr),
                    "--json",
                    "state,mergeable,statusCheckRollup,url",
                ],
                cwd=root,
            )
            meta = json.loads(pr.stdout)
            if meta.get("state") != "MERGED":
                # Wait for checks
                run(["gh", "pr", "checks", str(args.pr), "--watch"], cwd=root)
                run(
                    ["gh", "pr", "merge", str(args.pr), "--merge", "--delete-branch"],
                    cwd=root,
                )
            run(["git", "checkout", "main"], cwd=root)
            run(["git", "pull", "origin", "main"], cwd=root)
            steps.append(StepResult("merge", True, meta.get("url", f"pr#{args.pr}")))

        head_sha = run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()

        engine_ref = ""
        web_ref = ""
        if not args.from_smoke and not args.skip_publish_wait:
            log("==> Wait/publish digests")
            # Publish triggers on main push; poll up to ~15m
            deadline = time.time() + 900
            while True:
                try:
                    engine_ref, web_ref = find_publish_digests(root, head_sha)
                    break
                except RolloutError as exc:
                    if time.time() >= deadline:
                        raise
                    log(f"waiting_publish ({exc})")
                    time.sleep(20)
            steps.append(StepResult("publish", True, engine_ref))

        if not args.from_smoke and not args.skip_pin and engine_ref and web_ref:
            log("==> Pin production digests")
            branch = f"chore/pin-gate-10d-{head_sha[:7]}"
            run(["git", "checkout", "-B", branch], cwd=root)
            pin_blueprint(root, engine_ref, web_ref)
            run(
                [
                    python,
                    "scripts/validate_render_blueprint.py",
                    "render-production.yaml",
                    "--profile",
                    "production",
                ],
                cwd=root,
            )
            run(["git", "add", "render-production.yaml"], cwd=root)
            # commit may no-op if unchanged
            commit = run(
                [
                    "git",
                    "commit",
                    "-m",
                    "Pin Gate 10D production images for A/B framework.",
                ],
                cwd=root,
                check=False,
            )
            if commit.returncode == 0:
                run(["git", "push", "-u", "origin", "HEAD"], cwd=root)
                run(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--title",
                        "Pin Gate 10D production images",
                        "--body",
                        "## Summary\n- Pin Gate 10D digests for A/B admin routes.\n\n## Test plan\n- [ ] Render Sync\n- [ ] production-smoke --allow-active-canary\n",
                    ],
                    cwd=root,
                    check=False,
                )
                # merge latest pin pr from this branch
                run(["gh", "pr", "checks", "--watch"], cwd=root, check=False)
                run(["gh", "pr", "merge", "--merge", "--delete-branch"], cwd=root)
                run(["git", "checkout", "main"], cwd=root)
                run(["git", "pull", "origin", "main"], cwd=root)
                steps.append(StepResult("pin", True, "merged"))
            else:
                log("pin_commit_skipped (no changes or commit failed)")
                run(["git", "checkout", "main"], cwd=root, check=False)
                steps.append(StepResult("pin", True, "unchanged_or_skipped"))

        if not args.from_smoke and not args.skip_deploy:
            if not engine_ref or not web_ref:
                # read from blueprint
                bp = open(
                    os.path.join(root, "render-production.yaml"), encoding="utf-8"
                ).read()
                import re

                eng = re.search(r"saveiq-engine@(sha256:[a-f0-9]{64})", bp)
                web = re.search(r"saveiq-web@(sha256:[a-f0-9]{64})", bp)
                if not eng or not web:
                    raise RolloutError("cannot read pinned digests from blueprint")
                engine_ref = f"ghcr.io/leoly5945-hash/saveiq-engine@{eng.group(1)}"
                web_ref = f"ghcr.io/leoly5945-hash/saveiq-web@{web.group(1)}"
            deployed = maybe_deploy_via_render_api(engine_ref, web_ref)
            if not deployed:
                log(
                    "ACTION_REQUIRED: Sync Blueprint saveiq-production in Render, then re-run with --from-smoke"
                )
                steps.append(StepResult("deploy", False, "manual_sync_required"))
                # Continue to probe; may already be live from prior sync
            else:
                steps.append(StepResult("deploy", True, "render_api"))

        log("==> Wait for A/B routes")
        wait_for_abtest_route(api_url)

        token = require_admin_token()
        canary_before = snapshot_canary(api_url, token)

        log("==> Pre-enable smoke (A/B must be off; canary may stay at C2)")
        assert_abtest_off(api_url, token)
        run(
            [
                python,
                "scripts/production_smoke.py",
                "--api-url",
                api_url,
                "--web-url",
                web_url,
                "--require-admin",
                "--allow-active-canary",
            ],
            cwd=root,
        )
        steps.append(StepResult("smoke", True, "ok"))

        log("==> Start A/B experiment")
        started = http_json(
            f"{api_url}/admin/abtest/start",
            method="POST",
            token=token,
            body={"experiment": EXPERIMENT},
        )
        if not started.get("running"):
            raise RolloutError(f"failed to start A/B: {started}")
        log(f"abtest_started={json.dumps(started, sort_keys=True)}")
        steps.append(StepResult("abtest_start", True, EXPERIMENT))

        # Confirm canary unchanged
        canary_after_start = snapshot_canary(api_url, token)
        if canary_after_start.get("enabled") != canary_before.get(
            "enabled"
        ) or canary_after_start.get("percentage") != canary_before.get("percentage"):
            stop_abtest(api_url, token)
            raise RolloutError("canary config changed unexpectedly; aborted")

        traffic_groups: dict[str, int] = {}
        if not args.skip_traffic:
            log("==> Generate sticky traffic")
            traffic_groups = generate_traffic(
                api_url, users=args.users, requests_per_user=args.requests_per_user
            )
            log(f"traffic_groups={traffic_groups}")
            steps.append(StepResult("traffic", True, json.dumps(traffic_groups)))

        log("==> Collect stats / significance / metrics")
        status = http_json(f"{api_url}/admin/abtest/status", token=token)
        stats = status.get("stats") or http_json(
            # status already embeds stats; keep fallback shape
            f"{api_url}/admin/abtest/status",
            token=token,
        ).get("stats")
        # Prefer dedicated stats via status payload
        if not isinstance(stats, dict):
            stats = {"groups": {}}
        sig_url = (
            f"{api_url}/admin/abtest/significance?"
            f"{urllib.parse.urlencode({'experiment': EXPERIMENT, 'metric': 'conversions'})}"
        )
        try:
            significance = http_json(sig_url, token=token)
        except RolloutError as exc:
            # Older images may 500 on zero-conversion chi2; continue with stats-only decide.
            log(f"significance_request_failed={exc}")
            significance = {
                "error": str(exc),
                "significant": False,
                "p_value": None,
            }
        metric_counts = metrics_snapshot(api_url)
        log(f"abtest_stats={json.dumps(stats, sort_keys=True)}")
        log(f"abtest_significance={json.dumps(significance, sort_keys=True)}")
        log(f"metrics_labels={metric_counts}")

        decision, reason = decide(stats, significance)
        log(f"decision={decision} reason={reason}")
        steps.append(StepResult("decision", True, f"{decision}: {reason}"))

        # Default: stop after controlled probe. Keep only with --keep-running
        # (never keep when decision is stop_rollback).
        if decision == "stop_rollback" or not args.keep_running:
            stop_abtest(api_url, token)
            steps.append(StepResult("abtest_stop", True, f"stopped after {decision}"))
        else:
            log(f"keeping A/B running ({decision})")

        # Final canary unchanged check
        canary_final = snapshot_canary(api_url, token)
        if canary_final.get("enabled") != canary_before.get(
            "enabled"
        ) or canary_final.get("percentage") != canary_before.get("percentage"):
            raise RolloutError("canary drifted during rollout")

        log("gate10d_rollout=ok")
        for step in steps:
            log(f"step.{step.name}={'ok' if step.ok else 'fail'}:{step.detail}")
        return 0

    except Exception as exc:  # noqa: BLE001
        log(f"gate10d_rollout=error: {exc}")
        token = os.environ.get("ADMIN_API_TOKEN", "").strip()
        if token:
            # Best-effort A/B rollback only (never touch canary).
            try:
                stop_abtest(api_url, token)
            except Exception:  # noqa: BLE001
                pass
        for step in steps:
            log(f"step.{step.name}={'ok' if step.ok else 'fail'}:{step.detail}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
