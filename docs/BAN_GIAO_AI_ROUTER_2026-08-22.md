# Bàn giao dự án: AI Router cho Affiliate Network tại Canada

**Ngày bàn giao:** 2026-08-22  
**Dự án:** Dealhunter / SaveIQ — AI Router (affiliate, thị trường Canada)  
**Repo:** `leoly5945-hash/SaveIQ`  
**Thư mục local:** `/Users/duyluong/Downloads/Dealhunter AI plafform` (đúng repo; không dùng `b2b-rubber-automation`)

**Trạng thái tổng:** Production **live router + Chinese LLM + neural flag + RLHF flag** đã bật. Soak neural n10→n100 **PASS**. Runtime policy **`rlhf`** (canary nhãn 10%, chưa promote). **4 module bổ trợ đã code xong ở workspace, chưa merge/pin image production.** Gate 10I/10J **không bật**.

> ⚠️ **Cập nhật 2026-08-24:** RLHF đã **promote** (2026-08-23T12:44:27Z) và **Gate 10I đã merge** (PR #35, `FEATURE_KILL_SWITCH=true` armed, chưa trip). Chỉ còn Gate 10J (auto-tune) là chưa làm. File này giữ nguyên làm bản ghi ngày 2026-08-22; xem `lamviec.md` ở repo root để biết trạng thái runtime mới nhất — tài liệu đó được cập nhật liên tục bởi các agent, còn file này là snapshot tĩnh.

---

## 1. TỔNG QUAN DỰ ÁN

### 1.1 Mục tiêu

Xây dựng và triển khai **AI Router** cho nền tảng tiếp thị liên kết tại Canada:

- **Bandit** LinUCB → Neural → RLHF để chọn LLM provider trên đường parse intent (không phải % canary router).
- **Live AI providers**, DeepSeek bật (Chinese LLM).
- **4 module bổ trợ** (attribution, multi-objective, fraud, partner diversity) — code local; flag mặc định **tắt**.

### 1.2 Phạm vi

- Routing AI cho **intent parser** (OpenAI / Anthropic / DeepSeek / Qwen / Ernie / mock).
- Feature flags qua Render Blueprint (`render.yaml` staging, `render-production.yaml` prod).
- Admin API (`X-Admin-Token`) và Prometheus `/metrics`.
- Soak n10/n25/n50/n100 là **nhãn checkpoint** — `POST /admin/bandit/switch_policy` **không** nhận traffic %. Canary router **đã 100%** từ Gate 10G. `--mutate-canary` mặc định **tắt**.

### 1.3 Ngoài phạm vi (chưa làm / không bật)

- Gate **10I** kill switch, Gate **10J** auto-tune.
- Auto-tune **không được** flip `FEATURE_NEURAL_BANDIT`, `FEATURE_RLHF_ROUTER`, `BANDIT_POLICY`, Chinese LLM (`HUMAN_ONLY_FLAGS`).
- 4 module **chưa** có trên `origin/main` / image prod (xem §8).

---

## 2. CÁC GATE ĐÃ HOÀN THÀNH

| Gate | Tên | Trạng thái | Ghi chú |
|------|-----|------------|---------|
| **10E** | Canary + mock router | ✅ COMPLETE | Soak C4 ≥24h |
| **10F** | Global AI Router (mock) | ✅ COMPLETE | Superseded by 10G |
| **10G** | Live providers + Chinese / DeepSeek | ✅ COMPLETE | `AI_ROUTER_MODE=live`, `chinese=True` |
| **10H Neural** | Neural bandit prod | ✅ n10→n100 PASS | PR **#33** `FEATURE_NEURAL_BANDIT=true` |
| **10H RLHF** | RLHF prod | ✅ COMPLETE (2026-08-24 cập nhật) | PR **#34**; promoted 2026-08-23T12:44:27Z — xem `lamviec.md` |
| **10I** | Kill switch | ✅ COMPLETE (2026-08-24 cập nhật) | Merged PR **#35**; `FEATURE_KILL_SWITCH=true` armed, chưa trip; alias `/admin/kill-switch/*` chưa deploy image mới — xem `lamviec.md` |
| **10J** | Auto-tune | ⏸ PENDING | Stub: `docs/GATE_10J_AUTO_TUNE_CHECKLIST.md` |

Checklist chi tiết: `docs/GATE_10H_NEURAL_RLHF_CHECKLIST.md`. Runbook: `docs/RUNBOOK.md` §3h.

---

## 3. KIẾN TRÚC HỆ THỐNG

### 3.1 Luồng routing chính

```text
HTTP /search hoặc /recommendations
  → (optional) LLM intent parser
  → AiRouter.execute(RouteRequest)
       1. Cache Redis (TTL, Gate 10E có thể override)
       2. Rule chọn provider (_select_providers: cost/quality × complexity × Chinese)
       3. Bandit.decide (LinUCB / neural / RLHF tùy runtime policy)
       4. Partner modules (chỉ khi FEATURE_* bật hoặc provider bị block):
            fraud filter → multi-objective score → diversity weights
       5. Gọi provider; fallback nếu fail / confidence < 0.60
       6. Attribution.track_affiliate(user_id, provider) nếu FEATURE_ATTRIBUTION
  → Parser deterministic nếu router fail
```

Code:

| Thành phần | Path |
|------------|------|
| FastAPI app | `apps/api/app/main.py` |
| AI Router | `apps/api/app/services/router/ai_router.py` |
| Bandit | `apps/api/app/services/bandit/service.py` |
| 4 module | `src/affiliate/attribution_tracking.py`, `src/affiliate/fraud_detection.py`, `src/router/multi_objective.py`, `src/router/partner_diversity.py` |
| Path `src.*` | `apps/api/app/integrations/repo_src.py` |

**Lưu ý ngữ nghĩa:** “Partner” trên hot path hiện tại là **tên LLM provider** (`openai`, `deepseek`, …), không phải merchant affiliate trong Postgres. Catalog affiliate vẫn đi ingestion / search / click như Gate 4–5.

### 3.2 Môi trường

| | Staging | Production |
|---|---------|------------|
| Blueprint | `render.yaml` (`saveiq-staging`) | `render-production.yaml` (`saveiq-production`) |
| API | `https://dealhunter-staging-api.onrender.com` | `https://dealhunter-production-api.onrender.com` |
| Deploy | Render Sync; **`autoDeployTrigger: off`** | Giống staging — merge GitHub **không** tự deploy |
| Token | `STAGING_ADMIN_TOKEN` = Render staging `ADMIN_API_TOKEN` | `PROD_ADMIN_TOKEN` = Render **production** `ADMIN_API_TOKEN` (không dùng staging) |

Header admin: `X-Admin-Token`.

### 3.3 Feature flags (prod Blueprint sau PR #34)

| Flag | Prod | Ý nghĩa |
|------|------|---------|
| `FEATURE_AI_ROUTER` | `true` | Router bật |
| `AI_ROUTER_MODE` | `live` | Live providers |
| `FEATURE_CHINESE_LLM_PROVIDERS` | `true` | DeepSeek/Qwen/Ernie |
| `FEATURE_NEURAL_BANDIT` | `true` | Cho phép agent neural |
| `FEATURE_RLHF_ROUTER` | `true` | Cho phép agent RLHF |
| `BANDIT_POLICY` (Blueprint) | `linucb` | Default sau redeploy; runtime đang `rlhf` nhờ `switch_policy` |
| `FEATURE_BANDIT_ROUTER` | `false` | Bandit **logging**; `feature_enabled=false` — không cắt canary |
| `FEATURE_KILL_SWITCH` | `true` (cập nhật 2026-08-24, xem `lamviec.md`) | 10I — armed, chưa trip |
| `FEATURE_AUTO_TUNING` | `false` | 10J |
| `FEATURE_ATTRIBUTION` / `FRAUD` / `MULTI_OBJECTIVE` / `PARTNER_DIVERSITY` | **chưa có trên Blueprint** | Mặc định module = tắt |

Sau mỗi Render Sync, runtime policy **reset** về `BANDIT_POLICY` Blueprint (`linucb`) cho đến khi gọi lại `switch_policy`.

---

## 4. BỐN MODULE BỔ TRỢ

Code workspace (untracked `src/` + diff `apps/api`). **Chưa trên `origin/main`.** Production hiện **không** chạy bước 4–6 của §3.1 cho tới khi merge + pin image + Sync.

| Module | Admin API | Env | Hành vi khi tắt |
|--------|-----------|-----|-----------------|
| Attribution | `GET /admin/attribution/status`, `/report`, `/conversion_rate` | `FEATURE_ATTRIBUTION` | `track_affiliate` no-op |
| Multi-objective | `POST /admin/objective/update_weights` | `FEATURE_MULTI_OBJECTIVE` | `calculate_score` = raw conversion proxy |
| Fraud | `GET /admin/fraud/status`, `/metrics`; `POST /block`, `/unblock` | `FEATURE_FRAUD_DETECTION` | `is_fraudulent` = false; **block vẫn có hiệu lực** nếu đã block |
| Diversity | `GET /admin/diversity/status`; `POST /cap`, `/reset` | `FEATURE_PARTNER_DIVERSITY` | trả scores không đổi |

Singleton **dùng chung** admin ↔ `AiRouter` (`get_tracker` / `get_detector` / `get_optimizer` / `get_manager`).

Test: `apps/api/tests/test_router_module_admin.py`, `test_fraud_block_skips_primary_provider`, `test_attribution_records_provider_touch_on_success`.

Docker API: build context = **repo root**, `COPY src ./src` (`apps/api/Dockerfile`, `docker-compose.yml`, `.github/workflows/container-publish.yml`) — chỉ có hiệu lực sau khi các file này được merge.

---

## 5. ADMIN / MONITORING

| Surface | Việc |
|---------|------|
| `GET /admin/bandit/status` | `policy`, `flags.neural/rlhf`, `neural.ready`, `rlhf.ready` |
| `POST /admin/bandit/switch_policy` | `{"policy":"neural"|"rlhf"|"linucb"|"rule"}` — **không có %** |
| `GET /admin/router-status` | Router + `partner_modules` (khi image có integration) |
| `GET /admin/router/metrics` | Cache / provider |
| `GET /admin/safety/status` | Kill/autotune phải `false`, `tripped=false` |
| `GET /metrics` | Prometheus (5xx, histogram; `/search` p95 thường **trống** sau redeploy) |

Soak monitor: `scripts/gate10h_monitor_soak.py`  
- Neural: `--phase n10|n25|n50|n100`  
- RLHF canary: thêm `--expect-rlhf --allow-sparse-latency`

Ngưỡng soak: HTTP 5xx delta = 0, error rate &lt; 0.1%, p95 ≤ baseline × 1.10, cache &gt; 60%. `ready=false` = WARN. Histogram trống = WARN với `--allow-sparse-latency`.

---

## 6. LỊCH SOAK 10H (PRODUCTION)

| Phase | Bắt đầu | Kết thúc / ghi chú |
|-------|---------|-------------------|
| n10 | 2026-08-13T06:02Z | PASS; advance n25 2026-08-17 |
| n25 | 2026-08-17 | PASS 2026-08-19 (DNS local blips, `--once` PASS) |
| n50 | 2026-08-19T07:01Z | PASS ~31h; 4 DNS; advance n100 2026-08-20T14:37Z |
| n100 neural | 2026-08-20T14:37Z | `--once` PASS 2026-08-22T03:39Z |
| RLHF canary | **2026-08-22T03:58Z** | `policy=rlhf`, label 10%, canary % **không** đổi; `rlhf.ready=false`, samples=0 → LinUCB fallback |

Promote RLHF sớm nhất: **2026-08-23T03:58Z**, sau `--once --expect-rlhf` PASS:

```bash
cd "/Users/duyluong/Downloads/Dealhunter AI plafform"
source .venv/bin/activate
export PROD_ADMIN_TOKEN='...'   # production ADMIN_API_TOKEN

python3 scripts/gate10h_monitor_soak.py --phase n100 --once --allow-sparse-latency --expect-rlhf --report
python3 scripts/gate10h_prod_rlhf.py --stage promote --confirm-promote
```

Rollback (không tắt `FEATURE_AI_ROUTER`):

```bash
python3 scripts/gate10h_prod_rlhf.py --stage rollback --confirm-rollback
```

---

## 7. LỆNH VẬN HÀNH

Luôn `cd` đúng repo. zsh: **không** dán comment `#` trên cùng dòng lệnh.

```bash
cd "/Users/duyluong/Downloads/Dealhunter AI plafform"
source .venv/bin/activate
export PROD_ADMIN_TOKEN='...'

python3 scripts/gate10h_monitor_soak.py --phase n100 --status
python3 scripts/gate10h_prod_rlhf.py --stage verify --assume-synced
```

PR liên quan: [#33](https://github.com/leoly5945-hash/SaveIQ/pull/33) neural, [#34](https://github.com/leoly5945-hash/SaveIQ/pull/34) RLHF.

Validator prod (cả hai flag):  
`--allow-neural-bandit --allow-rlhf-router --allow-rlhf-after-neural`

---

## 8. VIỆC CÒN LẠI CHO NGƯỜI NHẬN

1. ~~Không bật 10I/10J cho đến khi 10H đóng~~ — **10H đã đóng, 10I đã merge (PR #35) 2026-08-24.** Còn lại: **không bật 10J** cho đến khi có quyết định riêng — xem `lamviec.md`.
2. ~~RLHF: chờ ≥24h → promote~~ — **đã promote** 2026-08-23T12:44:27Z.
3. **4 module:** commit/PR `src/` + `apps/api` integration + Docker context; pin image; Sync; **rồi mới** thêm flag Blueprint (từng cái, staging trước).
4. **Redeploy:** nhớ `switch_policy` lại `rlhf` hoặc `neural` nếu muốn giữ runtime (Blueprint vẫn `linucb`).
5. Histogram `/search` + `/recommendations` trống sau Sync là đã biết; dùng `--allow-sparse-latency`.
6. Token: Render production `ADMIN_API_TOKEN` → `PROD_ADMIN_TOKEN`. HTTP 401 `"Admin token is required."` = thiếu hoặc sai token.

---

## 9. RỦI RO ĐÃ BIẾT

- `rlhf.ready=false` / `neural.ready=false` (0 samples, `min_samples_ready` 25–30) → LinUCB fallback; `feature_enabled=false` = bandit log, không cắt canary.
- Soak JSONL FAIL vì DNS `nodename nor servname` hoặc 401 token — không phải 5xx prod.
- CI PR #34: pytest catalog mock stale + `npm audit` nanoid — **không** liên quan flag RLHF; đã merge `--admin`.
- Workspace còn file rubber / `bangiao.md` cũ (Gate 5E, 2026-08-06) / SSH key — **không commit**.

---

## 10. TÀI LIỆU

- `docs/GATE_10H_NEURAL_RLHF_CHECKLIST.md`
- `docs/GATE_10I_KILL_SWITCH_CHECKLIST.md` / `docs/GATE_10J_AUTO_TUNE_CHECKLIST.md`
- `docs/GATE_10G_CLOSEOUT.md`, `docs/GATE_10E_CLOSEOUT.md`
- `docs/RUNBOOK.md`
- `docs/ARCHITECTURE.md`

**Ký nhận:** AI Lead / Ops / Security — còn trống trên checklist 10H.
