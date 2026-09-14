# SaveIQ Chrome extension (MVP)

Shows SaveIQ's buy-now-or-wait verdict as a small card on Amazon.ca product
pages, without the copy-paste-into-saveiq.ca round trip. A thin client over
the existing public `/check` API — no new backend work.

## How it works

- `content.js` runs on any `amazon.ca` page, pulls the ASIN out of the URL
  (`/dp/`, `/gp/product/`, `/gp/aw/d/`), and asks the background worker for
  a verdict.
- `background.js` does the actual `fetch` to
  `https://dealhunter-production-api.onrender.com/check?product_id=<ASIN>`.
  This has to happen in the background service worker, not the content
  script: the API doesn't send `Access-Control-Allow-Origin` for a
  `chrome-extension://` origin (checked 2026-09-14), so a fetch from the
  page context would be CORS-blocked. The `host_permissions` entry in
  `manifest.json` is what lets the background worker's fetch bypass that.
- `overlay.css` isolates the injected card from Amazon's page styles with
  `all: initial` / `all: revert` (no Shadow DOM in this MVP — would be the
  next hardening step if Amazon's CSS ever leaks through).

## Load it locally (testing)

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. **Load unpacked** → select this `apps/extension/` folder.
4. Visit any `amazon.ca/dp/<ASIN>` product page — the card appears bottom-right
   within a couple seconds.

No build step — it's plain JS/CSS, loads as-is.

## Known gaps (fine for MVP, worth fixing before wider promotion)

- No Shadow DOM — a page whose CSS beats `!important` specificity could still
  bleed into the card. Low risk on Amazon's own pages, but worth doing if this
  ever runs on other retailers.
- No SPA-navigation handling — Amazon's product pages are full page loads, so
  this doesn't matter today, but if Amazon ever moves to client-side routing
  the content script would need a `MutationObserver` or history-API hook to
  re-run on navigation instead of only on load.
- No caching — every page view is a fresh `/check` call. Fine at current
  traffic; revisit if this becomes a meaningful chunk of API load.
- Icons are a placeholder "IQ" mark generated locally, not a real design.

## Publishing to the Chrome Web Store

1. Zip the folder contents (not the folder itself): from inside
   `apps/extension/`, `zip -r ../saveiq-extension.zip .`
2. Register a Chrome Web Store developer account ($5 USD one-time) at
   <https://chrome.google.com/webstore/devconsole>.
3. Upload the zip, fill in the listing (screenshots, description, privacy
   practices — this extension only ever talks to `dealhunter-production-api.onrender.com`,
   no user data collected), submit for review.
4. Review is typically a few days to a week.
