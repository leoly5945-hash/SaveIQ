# Archived: public-facing homepage prompt

Completed 2026-08-26. Original task: relocate the QA dashboard from `/` to
`/internal/staging-tools` and ship a simple public homepage at `/` plus `/privacy`.

The live prompt lived at `docs/CURSOR_PROMPT_public_homepage.md`.

---

## Context

Dealhunter/SaveIQ (`apps/web`, Next.js App Router, plain CSS, no component
library). Production web (`dealhunter-production-web.onrender.com`) currently
serves an **internal QA/testing dashboard** at `/` — `src/app/page.tsx` renders
`<SearchExperience searchEndpoint="/api/search" />` from
`src/app/search-experience.tsx` (2936 lines): mock-feed admin controls,
staging click analytics, recommendation-quality cockpit, retention tools, an
"Admin token" field, and the banner "Staging mock data only". This is real,
working internal tooling for the eng team — **do not delete or break it**,
just relocate it (see Task 1).

`render-production.yaml` currently sets `PRODUCTION_NOINDEX=true` — the site
is intentionally not public yet. **Do not touch this flag** as part of this
task; the operator flips it manually when ready to launch.

The backend API this page needs already exists and works — no backend
changes required:
- `POST /recommendations` (proxied by `apps/web/src/app/api/recommendations/route.ts`,
  already forwards body/headers as-is) — body
  `{ intent: string (3-240 chars), limit?: 1-10 default 5, anonymous_user_id?: string, market?: default "CA" }`.
  See `apps/api/app/api/routes/recommendations.py` for the exact
  `RecommendationResponse` / `RecommendationOfferResponse` shape — read it
  directly rather than guessing field names.
- `POST /clicks` — already proxied at `apps/web/src/app/api/clicks/route.ts`
  (with an existing `route.test.ts`) — body
  `{ offer_id: number, target_type: "product" | "affiliate", referrer?: string, anonymous_user_id?: string }`.
  Valid `target_type` values are exactly `"product"` and `"affiliate"` (see
  `apps/api/app/models/affiliate.py` `ClickTargetType`).

**Gotcha, verified by reading the code:** neither `api/recommendations/route.ts`
nor `api/clicks/route.ts` forwards the `X-Anonymous-User-Id` header to the
backend — they only pass through `Accept` / `content-type` (and `user-agent`
for clicks). So the anonymous ID **must** go in the JSON body
(`anonymous_user_id` field) on every call to these two proxies, not the
header — the header is silently dropped as currently written. Don't "fix"
the proxies to forward the header instead; just always populate the body
field client-side.

Existing convention in `search-experience.tsx` for how a result is opened
(mirror this, don't reinvent):
- The anchor `href` comes directly from the offer's `product_url` /
  `affiliate_url` field already present in the API response — do **not**
  wait on the `/clicks` response for a redirect URL.
- Click tracking is fire-and-forget on the `onClick` handler
  (`fetch("/api/clicks", { ..., keepalive: true })`, errors swallowed) — it
  must never block or delay opening the link.
- Anonymous ID: generated client-side and persisted (check how/if
  `search-experience.tsx` already does this; if not, use
  `crypto.randomUUID()` on first load, store in `localStorage`, reuse
  thereafter) — remember to put it in the request **body**, per the gotcha
  above.

## Product requirements (from the operator)

A **very simple** page: the user types what they want in one box, submits,
and gets results. Explicitly:
- **No user accounts / no login / no signup wall anywhere on this page.**
  Anonymous tracking only (see above) — this is a deliberate product
  decision already made, not an oversight.
- **Minimal visuals** — no hero image, no stock photography, no product
  thumbnails unless the API already returns one and it's small/optional.
  Text-forward: title, merchant, price, coupon/cashback badges as text, a
  "View deal" link. Avoid clutter.
- One free-text input (e.g. placeholder "What are you looking for?"), a
  submit button (and submit-on-Enter), a loading state, an empty/error
  state, and a results list.
- Mobile-responsive (single column is fine).
- Footer: a short **affiliate disclosure** and a link to `/privacy` (a
  Privacy Policy page — Canadian audience). Use this exact disclosure text
  unless the operator says otherwise:

  > "Some links on this page are affiliate links. If you make a purchase
  > through them, DealHunter may earn a commission at no extra cost to you."

  For `/privacy`, add a clearly-marked placeholder page (e.g. a banner at
  the top: "Draft — pending legal review") with a reasonable starter privacy
  policy (what's collected: anonymous usage/click data, no accounts, no
  sale of personal data, cookie/analytics disclosure, contact method TBD).
  **Do not present this as final legal advice** — flag it as a draft in
  the PR description too.

## Task

1. **Relocate the existing internal dashboard**, unchanged, to a new route
   — e.g. `src/app/internal/staging-tools/page.tsx` (adjust the path if a
   more idiomatic one fits the existing routing conventions better). Just
   move the composition (`page.tsx`'s JSX) there; `search-experience.tsx`
   itself shouldn't need logic changes. Confirm it still builds and its
   existing tests (`page.test.tsx` etc.) still pass after the move — update
   import paths/test paths as needed.
2. **Build the new public homepage** at `src/app/page.tsx`, per the product
   requirements above, calling `POST /api/recommendations` and
   `POST /api/clicks`. Add a `/privacy` route with the draft policy.
3. Keep `globals.css` changes scoped/additive — don't break the relocated
   internal dashboard's existing styles (check what className scoping it
   relies on before editing shared CSS).
4. Tests: add/update `.test.tsx` files mirroring the existing pattern
   (`page.test.tsx`, route `.test.ts` files) — cover the submit → loading →
   results flow, the empty/error states, and that clicking a result fires
   `/api/clicks` without blocking navigation.
5. Run and confirm clean: `npm run lint`, `npm run typecheck`,
   `npm run test`, `npm run build` (all from `apps/web`).

## Explicitly out of scope

- Any change to `render.yaml` / `render-production.yaml` (including
  `PRODUCTION_NOINDEX` — stays as-is).
- Any backend (`apps/api`) change — the APIs already do what's needed.
- User accounts, login, signup, any auth UI.
- The uncommitted `src/affiliate`, `src/router`,
  `apps/api/app/integrations` workstream — unrelated, don't touch.
- Anything under Gate 10I/10J (kill switch, auto-tune) — unrelated.

## Report back

What was created/moved, whether all four checks in step 5 pass, and a
screenshot or description of the new homepage's states (empty, loading,
results, error) if you can render one.
