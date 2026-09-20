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
