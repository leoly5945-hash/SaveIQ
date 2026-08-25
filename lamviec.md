# Làm việc — DealHunter / SaveIQ (handover cho Claude + DeepSeek)

Cập nhật: **2026-08-25** (Gate 10I complete; Gate 10J **staging dry-run exercised PASS** qua PR #37/#38, prod autotune vẫn false)  
Repo: `leoly5945-hash/SaveIQ` · Workspace local: `Dealhunter AI plafform` (typo `plafform`, không phải `platform`)  
Luôn `cd` đúng folder này. Operator hay lỡ chạy script trong `b2b-rubber-automation`.

Đọc file này **trước** khi sửa router, Blueprint, kill switch, hay Gate 10J.

---

## Trạng thái hiện tại (sự thật runtime)

| Thứ | Production | Staging |
| --- | --- | --- |
| API | `https://dealhunter-production-api.onrender.com` | `https://dealhunter-staging-api.onrender.com` |
| Web | `https://dealhunter-production-web.onrender.com` | `https://dealhunter-staging-web.onrender.com` |
| `FEATURE_AI_ROUTER` / mode | **true / live** | false / disabled (Blueprint) |
| Chinese LLM | **ON** | off |
| `FEATURE_NEURAL_BANDIT` | **true** | false |
| `FEATURE_RLHF_ROUTER` | **true** | false |
| Runtime bandit `policy` | **rlhf** (Blueprint `BANDIT_POLICY` vẫn `linucb`; runtime `switch_policy`. `rlhf.ready=false` → LinUCB fallback) | — |
| `FEATURE_KILL_SWITCH` | **true** (armed, **not tripped**) | true in `render.yaml`; staging drill PASS |
| `FEATURE_AUTO_TUNING` | **false** — **không bật** (Gate 10J) | false |
| Canary | enabled **100%** (prod) | 0 sau drill |
| Image `/admin/kill-switch/*` | **live** digest `e0ed9382…667a7cd8` (PR #36 pin + Sync). OpenAPI có status/enable/disable | same API digest in `render.yaml` |

PR Gate 10I flag: **https://github.com/leoly5945-hash/SaveIQ/pull/35** — Merged.  
PR pin image: **https://github.com/leoly5945-hash/SaveIQ/pull/36** — Merged 2026-08-24.  
`prod-verify` **PASS** 2026-08-24T08:53Z trên image 10I (`env_flag=true`, `armed=true`, `tripped=false`, router live, **không** `pre-10I`). `monitor` PASS trước pin; nên chạy lại sau image mới.

Gate **10H** Neural + RLHF: ENABLEMENT COMPLETE (2026-08-23).  
Gate **10J** auto-tune: **staging dry-run exercised PASS** 2026-08-25 (PR #37/#38); production **CHƯA LÀM**, vẫn chờ sign-off riêng.

---

## Gate 10I — đã xong gì

1. Code: trip kill → fallback parser (`kill_switch_forces_router_fallback` trong `ai_router` / `canary/effective`). Alias `/admin/kill-switch/enable|disable|status`. Script `scripts/gate10i_kill_switch.py`.
2. Staging drill PASS (image cũ): trip qua `/admin/safety/kill/*`, seed canary 5% → 0, restore, audit.
3. Prod Blueprint `FEATURE_KILL_SWITCH=true`, autotune vẫn `false`. `FEATURE_AI_ROUTER` **không** tắt.
4. Monitor prod: `tripped=False`, `http_5xx=0`.

**Image 10I đã publish** (GHCR, không cần build local):

`ghcr.io/leoly5945-hash/saveiq-engine@sha256:e0ed93821f953537d2b4a3c122b644aeecf03e8074e9111d622d4635667a7cd8`

Pin trong `render.yaml` + `render-production.yaml`. **Đã live trên prod** (OpenAPI `/admin/kill-switch/*`). Web digest không đổi.

Emergency: `POST /admin/kill-switch/enable` (mặc định `trip=true`) hoặc `/admin/safety/kill/trip`. Trip trên image này **fallback parser**.

Auth: header `X-Admin-Token` = Render env `ADMIN_API_TOKEN` của **đúng** service (staging ≠ prod).

---

## Việc tiếp theo (ưu tiên)

1. **Gate 10I prod-drill — ĐÃ XONG, PASS** 2026-08-25: trip → canary 100→0 + router fallback xác nhận → disarm ngay → canary phục hồi 100 → 4 audit events. Kill switch đã được chứng minh hoạt động thật trên production.
2. **Gate 10J staging exercise — ĐÃ XONG** 2026-08-25 (PR #37 bật thử + PR #38 trả lại `false`): `evaluate` quan sát đúng 1 đề xuất propose-only (`cache_ttl_seconds 300→270`, lý do `latency_headroom`), `applied=false`, 0 audit `hparams_update`.
3. **Gate 10J production — đang triển khai** (operator đã xác nhận, 2026-08-25): bật `FEATURE_AUTO_TUNING=true` trên `render-production.yaml` với `AUTO_TUNE_DRY_RUN=true` (chỉ đề xuất, giống hệt staging) — **không** chuyển `dry_run=false` trừ khi có xác nhận riêng.
4. Affiliate modules dưới `src/` + Docker context `COPY src` là **uncommitted**, **không** nằm trong PR #35/#36/#37/#38. Đừng trộn.

---

## Lệnh operator

```bash
cd "/Users/duyluong/Downloads/Dealhunter AI plafform"
export PROD_ADMIN_TOKEN='...'      # dealhunter-production-api → ADMIN_API_TOKEN
export STAGING_ADMIN_TOKEN='...'   # dealhunter-staging-api → ADMIN_API_TOKEN
# zsh: KHÔNG ghi # comment cùng dòng export (sẽ lỗi `export: not valid in this context`)

make gate10i-kill-switch ARGS='--stage check'
make gate10i-kill-switch ARGS='--stage prod-verify --assume-synced'
make gate10i-kill-switch ARGS='--stage monitor --target prod'

# Gate 10J staging dry-run only (never production):
make gate10j-auto-tune ARGS='--stage check'
make gate10j-auto-tune ARGS='--stage staging-dry-run'
make gate10j-auto-tune ARGS='--stage evaluate'
```

Smoke sau 10I: `scripts/production_smoke.py --allow-kill-switch --allow-live-router --allow-chinese-providers`  
Validator prod: `--allow-neural-bandit --allow-rlhf-router --allow-rlhf-after-neural --allow-kill-switch`

---

## Render / Blueprint (bẫy đã gặp)

- Prod `autoDeployTrigger: off`. Đổi `FEATURE_*` **không** edit được trên Environment nếu biến đến từ Blueprint — phải **commit `main` + Manual Sync** Blueprint `saveiq-production`.
- Staging Postgres **Free expired** (2026-08-23): không Resume; đã **upgrade paid**. API timeout `/health` 0 byte khi DB chết. Staging-web free vẫn hay ngủ.
- Sync Blueprint **trước khi merge PR** = env vẫn `false`. Verify `env_flag=False` là đúng.
- CI `api` fail test catalog mock cũ; `security` fail `npm audit` nanoid — **cùng pattern PR #33/#34**. 10I merge `--admin` là có chủ ý.

Repo GitHub: Blueprint đọc `main`. Local confirm-kill không đủ.

---

## Token / HTTP

- Token prod ~64 hex, `ascii True`. Staging cũng vậy.
- Placeholder tiếng Việt (`dán-token-từ-...`) → `UnicodeEncodeError latin-1` trên `X-Admin-Token`.
- Sai token staging/prod → HTTP 401 `"Admin token is required."` (cả missing lẫn wrong).
- **Không** paste token vào chat / markdown / git.

---

## Kiến trúc kill switch (đúng code, đừng bịa endpoint)

- Env: `FEATURE_KILL_SWITCH` (Render). API **không** set process env.
- Runtime overlay Redis/memory: `safety:config:v1` (`kill_switch_enabled`, `tripped`, …).
- Trip actions mặc định: `stop_abtest`, `zero_canary`, `disable_autotune`, `reset_hparams`, `fallback_router`.
- Human-only (autotune **không** được flip): `feature_neural_bandit`, `feature_rlhf_router`, `feature_chinese_llm_providers`, `bandit_policy`.
- Rollback 10I: Blueprint `FEATURE_KILL_SWITCH=false` + `POST .../kill/disarm`. **Không** tắt `FEATURE_AI_ROUTER`.
- `percentage or -1` là bug Python (`0` falsy) — đã sửa trong `gate10i_kill_switch.py` (`canary_percentage`).

Files chính:

- `apps/api/app/api/routes/admin_safety.py`
- `apps/api/app/services/safety/service.py`
- `apps/api/app/services/canary/effective.py`
- `apps/api/app/services/router/ai_router.py` (`_router_active` / `_kill_switch_tripped`)
- `scripts/gate10i_kill_switch.py`
- `docs/RUNBOOK.md` §3d / §3i
- `render-production.yaml` / `render.yaml`

---

## Gate 10H (ngữ cảnh, đừng revert)

- Neural n10→n100 soak PASS; RLHF PR #33/#34; runtime `policy=rlhf`, `promoted_at=2026-08-23T12:44:27Z`.
- `switch_policy` **không** có traffic %. Canary đã 100% từ 10G.
- Surgical rollback bandit: `POST /admin/bandit/switch_policy {"policy":"linucb"}`.

---

## Việc **không** commit / không đụng

- `rubber_*`, `rubber_automator/`, SSH keys, `bangiao.md` (Gate 5E cũ), `tiep.md`, `data/`, `input_data.json`
- Secrets `.env`
- Untracked `src/affiliate`, `src/router`, `apps/api/app/integrations/` (affiliate admin) — workspace only, **không** trong origin/main sau #35

---

## Quy ước agent

- urllib + `X-Admin-Token`, không thêm `requests` vào API extra nếu không cần.
- Dry-run trước; `--confirm-*` mới ghi Blueprint / trip.
- Một flag một lần trừ neural+RLHF sau n100.
- Không bịa `/admin/latency`. Metrics: `GET /metrics`.
- Không enable 10J trong PR “tiện tay”.
- zsh: comment `#` không trên cùng dòng lệnh.
- Commit chỉ khi operator yêu cầu.

Checklist Gate 10I (chi tiết, một phần stale): `docs/GATE_10I_KILL_SWITCH_CHECKLIST.md`  
State local: `artifacts/gate10i_kill_switch_state.json`
