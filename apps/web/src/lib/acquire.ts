import { getApiBaseUrl } from "@/lib/config";

// mirrors app/services/acquisition (compare.py / tco.py)

export type AcquisitionKind =
  | "retail"
  | "financing"
  | "lease"
  | "bundle"
  | "refurb";

export type TCOBreakdown = {
  option_label: string;
  kind: AcquisitionKind;
  horizon_months: number;
  upfront_cents: number;
  device_cost_cents: number;
  plan_cost_cents: number;
  resale_credit_cents: number;
  nominal_total_cents: number;
  effective_total_cents: number;
  monthly_equivalent_cents: number;
  owns_at_horizon: boolean;
  assumptions: string[];
};

export type PathRecommendation = {
  product_slug: string | null;
  horizon_months: number;
  ranked: TCOBreakdown[];
  best_label: string;
  runner_up_gap_cents: number;
  caveats: string[];
  verify_first: string[];
};

export type AcquireResult = {
  product_id: string;
  title: string | null;
  category: string;
  recommendation: PathRecommendation;
};

export type AcquireProfile = {
  horizonMonths?: number;
  isBusiness?: boolean;
  annualDiscountRate?: number;
};

export const KIND_LABEL: Record<AcquisitionKind, string> = {
  retail: "Buy outright",
  financing: "Finance",
  lease: "Lease / return",
  bundle: "Bundle",
  refurb: "Refurbished",
};

function toParams(input: string, profile: AcquireProfile): URLSearchParams {
  const value = input.trim();
  const p = new URLSearchParams();
  if (/^[A-Za-z0-9]{10}$/.test(value)) p.set("product_id", value.toUpperCase());
  else p.set("url", value);
  p.set("horizon_months", String(profile.horizonMonths ?? 36));
  if (profile.isBusiness) p.set("is_business", "true");
  if (profile.annualDiscountRate)
    p.set("annual_discount_rate", String(profile.annualDiscountRate));
  return p;
}

export async function requestAcquire(
  input: string,
  profile: AcquireProfile = {},
  fetchImpl: typeof fetch = fetch
): Promise<AcquireResult | null> {
  try {
    const res = await fetchImpl(`/api/acquire?${toParams(input, profile)}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    return (await res.json()) as AcquireResult;
  } catch {
    return null;
  }
}

export async function fetchAcquireByAsin(
  asin: string,
  profile: AcquireProfile = {}
): Promise<AcquireResult | null> {
  try {
    const url = new URL("/acquire", getApiBaseUrl());
    url.search = toParams(asin, profile).toString();
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return (await res.json()) as AcquireResult;
  } catch {
    return null;
  }
}
