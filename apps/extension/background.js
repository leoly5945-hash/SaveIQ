// Fetches SaveIQ's /check result on behalf of the content script.
//
// This runs in the service worker, not the page — that's deliberate. The API
// doesn't send an Access-Control-Allow-Origin header for a chrome-extension://
// origin (confirmed 2026-09-14), so a fetch from the content script's page
// context would be blocked by CORS. A fetch from here, with `host_permissions`
// declared in the manifest for this exact host, bypasses that restriction.

const API_BASE = "https://dealhunter-production-api.onrender.com";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "SAVEIQ_CHECK") return false;

  const url = new URL(`${API_BASE}/check`);
  url.searchParams.set("product_id", message.asin);

  fetch(url, { headers: { Accept: "application/json" } })
    .then(async (res) => {
      if (!res.ok) {
        sendResponse({ ok: false, status: res.status });
        return;
      }
      const data = await res.json();
      sendResponse({ ok: true, data });
    })
    .catch((err) => {
      sendResponse({ ok: false, error: String(err) });
    });

  return true; // keep the message channel open for the async response
});
