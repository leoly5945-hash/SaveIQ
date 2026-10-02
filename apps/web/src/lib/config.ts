export function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function getBrandName() {
  return process.env.NEXT_PUBLIC_BRAND_NAME ?? "SaveIQ";
}

/** Canonical public origin, used for robots.txt / sitemap.xml absolute URLs. */
export function getSiteUrl() {
  return (
    process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ??
    "https://www.saveiq.ca"
  );
}

/** Public contact address shown on the site (routed by Cloudflare Email Routing). */
export const CONTACT_EMAIL = "info@saveiq.ca";

/**
 * Public Cloudflare Web Analytics site token (cookie-free traffic counts).
 * Leave empty to disable the beacon entirely.
 */
export const CLOUDFLARE_ANALYTICS_TOKEN = "a1a5b06db6e3439298bb8030b4189f18";

/** Amazon Associates tag, used only when the click-logging API can't answer. */
export function getAmazonTag() {
  return process.env.NEXT_PUBLIC_AMAZON_TAG ?? "saveiq-20";
}

/**
 * `rel` for a buy link. Links to our own `/go/…` hop must NOT carry
 * `noreferrer`: the hop reads the Referer header to record which SaveIQ page
 * the click came from, and with `noreferrer` the browser sends none (19 of 22
 * logged clicks had no page). The hop itself answers with
 * `Referrer-Policy: no-referrer`, so the retailer still never sees our URL.
 * A link that goes straight to another site keeps `noreferrer`.
 */
export function buyLinkRel(href: string | null | undefined): string {
  return href && href.startsWith("/go/")
    ? "sponsored nofollow noopener"
    : "sponsored nofollow noopener noreferrer";
}
