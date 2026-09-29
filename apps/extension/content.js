// Detects the ASIN on an Amazon.ca product page and shows SaveIQ's verdict
// as a small floating card. No SPA route-watching in this MVP — Amazon
// product pages are full navigations, so a fresh content-script run per page
// load is enough.

const ASIN_RE = /\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})(?:[/?]|$)/;

const VERDICT_LABEL = {
  BUY: "Buy now",
  WAIT: "Wait",
  FAIR: "Fair price",
  UNKNOWN: "Not enough data",
};

function extractAsin(pathname) {
  const match = ASIN_RE.exec(pathname);
  return match ? match[1] : null;
}

function formatMoney(cents, currency) {
  if (typeof cents !== "number") return null;
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(cents / 100);
}

// `reason` and `cheapest.merchant` come from our own API, but merchant names
// ultimately trace back to scraped Google Shopping listings — untrusted text,
// same as any other third-party string. Escape before it goes into innerHTML.
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Mount `card` unless one is already showing. Only a real verdict may replace
// an error card, never the other way round, so a late failure can't sit on top
// of (or duplicate) a good card — e.g. when two copies of the extension are
// installed and both answer for the same page.
function mountCard(card, { replaceError }) {
  const existing = document.getElementById("saveiq-card");
  if (existing) {
    if (!replaceError || !existing.classList.contains("saveiq-error")) return;
    existing.remove();
  }
  card.querySelector(".saveiq-close").addEventListener("click", () => card.remove());
  document.body.appendChild(card);
}

function renderCard(data) {
  const verdict = data?.assessment?.verdict ?? "UNKNOWN";
  const price = formatMoney(data?.assessment?.effective_price?.effective_cents, data?.currency);
  const reason = data?.assessment?.reasons?.[0] ?? null;
  const cheapest = data?.comparison?.cheapest;
  const checkUrl = `https://www.saveiq.ca/check/${data.provider_product_id}`;

  const card = document.createElement("div");
  card.id = "saveiq-card";
  card.className = `saveiq-card saveiq-${verdict.toLowerCase()}`;

  const cheaperLine =
    cheapest && cheapest.url
      ? `<a class="saveiq-cheaper" href="${cheapest.url}" target="_blank" rel="sponsored noreferrer">
          Cheaper at ${escapeHtml(cheapest.merchant)}: ${formatMoney(
            cheapest.price_cents,
            cheapest.currency,
          )}
        </a>`
      : "";

  card.innerHTML = `
    <button class="saveiq-close" aria-label="Dismiss">&times;</button>
    <div class="saveiq-brand">SaveIQ</div>
    <div class="saveiq-verdict">${VERDICT_LABEL[verdict] ?? verdict}</div>
    ${price ? `<div class="saveiq-price">${price}</div>` : ""}
    ${reason ? `<div class="saveiq-reason">${escapeHtml(reason)}</div>` : ""}
    ${cheaperLine}
    <a class="saveiq-link" href="${checkUrl}" target="_blank" rel="noreferrer">See full comparison →</a>
  `;

  mountCard(card, { replaceError: true });
}

function renderError() {
  const card = document.createElement("div");
  card.id = "saveiq-card";
  card.className = "saveiq-card saveiq-unknown saveiq-error";
  card.innerHTML = `
    <button class="saveiq-close" aria-label="Dismiss">&times;</button>
    <div class="saveiq-brand">SaveIQ</div>
    <div class="saveiq-reason">No price history yet for this product.</div>
  `;
  mountCard(card, { replaceError: false });
}

function main() {
  const asin = extractAsin(window.location.pathname);
  if (!asin || document.getElementById("saveiq-card")) return;

  chrome.runtime.sendMessage({ type: "SAVEIQ_CHECK", asin }, (response) => {
    if (chrome.runtime.lastError || !response?.ok) {
      renderError();
      return;
    }
    renderCard(response.data);
  });
}

main();
