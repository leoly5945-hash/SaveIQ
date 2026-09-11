import { getApiBaseUrl } from "@/lib/config";

// --- types (mirror app/services/decision/deal_score.py) ---------------------

export type Verdict = "BUY" | "WAIT" | "FAIR" | "UNKNOWN";

export type WindowStat = {
  days: number;
  sample_count: number;
  min_cents: number | null;
  max_cents: number | null;
  avg_cents: number | null;
  median_cents: number | null;
};

export type PriceIntelligence = {
  currency: string;
  series_kind: string;
  total_points: number;
  coverage_days: number;
  current_cents: number | null;
  windows: Record<string, WindowStat>;
  all_time_min_cents: number | null;
  all_time_max_cents: number | null;
  current_percentile_90d: number | null;
  is_all_time_low: boolean;
  source_observations: number | null;
  lifetime_observations: number | null;
  provider_stats: Record<string, number | null>;
};

export type EffectivePrice = {
  base_price_cents: number;
  effective_cents: number;
  currency: string;
  components: { label: string; amount_cents: number }[];
};

export type DealAssessment = {
  verdict: Verdict;
  score: number;
  confidence: "high" | "medium" | "low";
  reasons: string[];
  effective_price: EffectivePrice;
  intelligence: PriceIntelligence;
};

export type SparkPoint = { t: string; c: number };

export type MerchantOffer = {
  merchant: string;
  price_cents: number;
  currency: string;
  url: string | null;
  match_confidence: number;
};

export type Comparison = {
  reference_merchant: string;
  reference_price_cents: number;
  currency: string;
  offers: MerchantOffer[];
  cheapest: MerchantOffer | null;
};

export type SpreadTier = {
  condition: "new" | "used";
  lowest_total_cents: number;
  offer_count: number;
  fba_available: boolean;
};

export type AmazonSpread = {
  buy_box_cents: number;
  currency: string;
  lowest_overall_cents: number;
  savings_vs_buy_box_cents: number;
  tiers: SpreadTier[];
};

export type CheckResult = {
  provider: string;
  provider_product_id: string;
  title: string | null;
  product_url: string | null;
  /** Affiliate-tagged buy link (Associates tag + SubID); falls back to product_url. */
  buy_url: string | null;
  currency: string;
  assessment: DealAssessment;
  sparkline: SparkPoint[];
  comparison: Comparison | null;
  spread: AmazonSpread | null;
  narration: string | null;
};

export type CheckOutcome =
  | { ok: true; result: CheckResult }
  | { ok: false; status: number; detail: string };

export type AlertKind = "any_drop" | "below" | "at_or_below_average";

export type CreateAlertOutcome =
  | { ok: true; unsubscribeUrl: string; baselineCents: number | null }
  | { ok: false; status: number; detail: string };

// --- presentation helpers -------------------------------------------------

export const VERDICT_COPY: Record<
  Verdict,
  { label: string; tone: "good" | "warn" | "neutral" | "unknown"; blurb: string }
> = {
  BUY: {
    label: "Buy",
    tone: "good",
    blurb: "This is a good price versus its recent history.",
  },
  WAIT: {
    label: "Wait",
    tone: "warn",
    blurb: "It has been cheaper recently — worth waiting for a dip.",
  },
  FAIR: {
    label: "Fair",
    tone: "neutral",
    blurb: "About the usual price. No urgency either way.",
  },
  UNKNOWN: {
    label: "Not enough data",
    tone: "unknown",
    blurb: "We don't have enough price history to call this one yet.",
  },
};

export function formatMoney(cents: number | null, currency: string): string {
  if (cents === null) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(
    cents / 100
  );
}

export function ninetyDayBand(
  intel: PriceIntelligence
): { min: number | null; max: number | null; avg: number | null } {
  const w = intel.windows["90"];
  const ps = intel.provider_stats ?? {};
  return {
    min: w?.min_cents ?? null,
    max: w?.max_cents ?? null,
    avg: ps["avg90_cents"] ?? w?.avg_cents ?? null,
  };
}

/** Looks enough like an Amazon URL or a bare ASIN to be worth submitting. */
export function looksSubmittable(value: string): boolean {
  const v = value.trim();
  if (/^[A-Za-z0-9]{10}$/.test(v)) return true;
  return /amazon\.[a-z.]+\/|amzn\.to\/|a\.co\//i.test(v);
}

// --- client (browser) via the same-origin proxy -------------------------

export async function requestCheck(
  input: string,
  fetchImpl: typeof fetch = fetch
): Promise<CheckOutcome> {
  const value = input.trim();
  const params = new URLSearchParams({ narrate: "1" });
  if (/^[A-Za-z0-9]{10}$/.test(value)) {
    params.set("product_id", value.toUpperCase());
  } else {
    params.set("url", value);
  }
  try {
    const res = await fetchImpl(`/api/check?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
    const body = (await res.json()) as
      | CheckResult
      | { detail?: string | { msg?: string }[] };
    if (!res.ok) {
      return { ok: false, status: res.status, detail: detailText(body) };
    }
    return { ok: true, result: normalizeResult(body as CheckResult) };
  } catch {
    return { ok: false, status: 0, detail: "Couldn't reach the price checker." };
  }
}

/** Tolerate an API that predates the sparkline / currency / comparison / spread fields. */
export function normalizeResult(r: CheckResult): CheckResult {
  return {
    ...r,
    currency: r.currency ?? r.assessment?.effective_price?.currency ?? "CAD",
    sparkline: Array.isArray(r.sparkline) ? r.sparkline : [],
    comparison: r.comparison ?? null,
    spread: r.spread ?? null,
    narration: r.narration ?? null,
    buy_url: r.buy_url ?? r.product_url ?? null,
  };
}

export async function requestCreateAlert(
  input: { productInput: string; email: string; kind?: AlertKind },
  fetchImpl: typeof fetch = fetch
): Promise<CreateAlertOutcome> {
  const value = input.productInput.trim();
  const payload: Record<string, string> = { email: input.email.trim() };
  if (/^[A-Za-z0-9]{10}$/.test(value)) {
    payload.product_id = value.toUpperCase();
  } else {
    payload.url = value;
  }
  payload.kind = input.kind ?? "any_drop";
  try {
    const res = await fetchImpl("/api/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const body = (await res.json()) as {
      unsubscribe_url?: string;
      baseline_cents?: number | null;
      detail?: string | { msg?: string }[];
    };
    if (!res.ok) {
      return { ok: false, status: res.status, detail: detailText(body) };
    }
    return {
      ok: true,
      unsubscribeUrl: body.unsubscribe_url ?? "",
      baselineCents: body.baseline_cents ?? null,
    };
  } catch {
    return { ok: false, status: 0, detail: "Couldn't set the alert." };
  }
}

function detailText(body: unknown): string {
  const d =
    body && typeof body === "object" && "detail" in body
      ? (body as { detail?: unknown }).detail
      : undefined;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && typeof d[0]?.msg === "string") {
    return d[0].msg as string;
  }
  return "Something went wrong. Try a different link.";
}

// --- server (SEO pages) — direct to the API ----------------------------

export async function fetchCheckByAsin(asin: string): Promise<CheckResult | null> {
  try {
    const url = new URL("/check", getApiBaseUrl());
    url.searchParams.set("product_id", asin.toUpperCase());
    url.searchParams.set("narrate", "1");
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      // Keep in sync with `revalidate` on check/[asin]/page.tsx.
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return normalizeResult((await res.json()) as CheckResult);
  } catch {
    return null;
  }
}
