# Gate 8 Closeout — Personalization & User Context

Date: 2026-08-06  
Branch: `feature/gate-8-personalization`

## Summary

Gate 8 adds **anonymous personalization** for recommendations and bandit context.
Defaults remain safe:

| Flag | Default |
|---|---|
| `FEATURE_PERSONALIZATION` | `false` |

When disabled, recommendation/click/bandit paths behave as before (non-personalized).

## Delivered

1. **Schema** — `anonymous_users`, `user_events`, optional `affiliate_click_events.anonymous_user_id`
2. **UserProfileService** — Redis-cached profiles, opt-out, event updates, hash embeddings (dim=8)
3. **PII policy** — opaque `X-Anonymous-User-Id` only (`[A-Za-z0-9_-]{8,64}`); rejects email/phone-like IDs
4. **Bandit features** — session/click/query norms + embedding slots appended to context vector
5. **Recommendation boost** — preferred-category soft re-rank when personalization active
6. **APIs**
   - `GET /user/profile`, `POST /user/feedback`, `POST /user/opt-out`, `POST /user/recommendations`
   - `GET /personalization/status`
   - `GET /admin/users/stats`
   - Web proxies: `/api/user/profile`, `/api/user/feedback`, `/api/personalization/status`
7. **Reward hook** — optional `BANDIT_REWARD_DELTA` * `user_satisfaction` (default delta=0)
8. **Smoke** — soft-skip until deployed; profile probe only when feature enabled

## Safety

- Feature default off
- No email/phone/name storage
- Opt-out disables personalization_active immediately
- Failures in profile load never break recommendations

## Follow-ups

- Replace hash embeddings with collaborative MF when corpus is large
- Delayed bandit reward updates from click/feedback attribution windows
- Signed anonymous cookies (still no PII) if product wants sticky IDs without client storage
