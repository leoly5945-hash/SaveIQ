# Làm việc — DealHunter / SaveIQ (handover cho Claude + DeepSeek)

Cập nhật: **2026-08-24 08:35 UTC** (sau Gate 10I prod-verify + monitor PASS)  
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
| Image `/admin/kill-switch/*` | Pin digest `e0ed9382…667a7cd8` (GHCR after #35). **Live after Render Sync of pin PR.** | same API digest in `render.yaml` |

PR Gate 10I: **https://github.com/leoly5945-hash/SaveIQ/pull/35** — **Merged** vào `main`.  
Sync Blueprint production: **done**. `prod-verify` + `monitor` **PASS** 2026-08-24.

Gate **10H** Neural + RLHF: ENABLEMENT COMPLETE (2026-08-23).  
Gate **10J** auto-tune: **CHƯA LÀM**.

---

## Gate 10I — đã xong gì

1. Code: trip kill → fallback parser (`kill_switch_forces_router_fallback` trong `ai_router` / `canary/effective`). Alias `/admin/kill-switch/enable|disable|status`. Script `scripts/gate10i_kill_switch.py`.
2. Staging drill PASS (image cũ): trip qua `/admin/safety/kill/*`, seed canary 5% → 0, restore, audit.
3. Prod Blueprint `FEATURE_KILL_SWITCH=true`, autotune vẫn `false`. `FEATURE_AI_ROUTER` **không** tắt.
4. Monitor prod: `tripped=False`, `http_5xx=0`.

**Image 10I đã publish** (GHCR, không cần build local):

`ghcr.io/leoly5945-hash/saveiq-engine@sha256:e0ed93821f953537d2b4a3c122b644aeecf03e8074e9111d622d4635667a7cd8`

Pin trong `render.yaml` + `render-production.yaml`. **Chưa live trên Render** cho đến khi merge pin PR + Manual Sync staging **và** production. Web digest không đổi.

Khẩn cấp trước Sync pin: `/admin/safety/kill/*`. Sau Sync: `/admin/kill-switch/*` + router fallback khi trip.

Auth: header `X-Admin-Token` = Render env `ADMIN_API_TOKEN` của **đúng** service (staging ≠ prod).

---

## Việc tiếp theo (ưu tiên)

1. **Không** chạy `--stage prod-drill` trừ khi operator chủ động cắt traffic (zero canary + fallback router).
2. **Không** bật `FEATURE_AUTO_TUNING` / Gate 10J cho đến khi 10I đứng (kill armed + image 10I nếu muốn alias).
3. **Pin API digest 10I** (branch `chore/pin-gate-10i-api-image`): merge PR → Render Manual Sync **saveiq** (staging) và **saveiq-production**. Rồi `prod-verify` — hết WARN `pre-10I image`.
4. Cập nhật checklist `docs/GATE_10I_KILL_SWITCH_CHECKLIST.md` (Blueprint **true**, enablement complete; còn ô Sync digest).
5. Affiliate modules dưới `src/` + Docker context `COPY src` là **uncommitted**, **không** nằm trong PR #35 / pin PR. Đừng trộn vào 10J.

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
