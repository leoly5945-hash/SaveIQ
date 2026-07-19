export function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function getBrandName() {
  return process.env.NEXT_PUBLIC_BRAND_NAME ?? "DealHunter";
}
