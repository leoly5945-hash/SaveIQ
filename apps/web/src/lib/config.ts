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
