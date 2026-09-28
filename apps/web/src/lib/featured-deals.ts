import { getApiBaseUrl } from "@/lib/config";

export const FEATURED_DEALS_HEADING = "Recently checked prices";
export const FEATURED_DEALS_BLURB =
  "Real products we price-checked by hand, across everyday categories. Prices are a snapshot from the date shown — always confirm the current price at the retailer before you buy.";
export const AMAZON_ASSOCIATE_DISCLOSURE =
  "As an Amazon Associate, SaveIQ earns from qualifying purchases.";

export const PRICE_DROPS_HEADING = "Near their 90-day low today";
export const PRICE_DROPS_BLURB =
  "Products on our Price Watch list whose Amazon.ca price, re-checked this morning, is at least 5% under their 90-day average and within 5% of their lowest price in the last 90 days — the same rule behind a Buy verdict in our Price Check. Price history from Keepa. Prices move during the day, so confirm at the retailer before you buy.";
export const PRICE_DROPS_EMPTY =
  "None of the products on our Price Watch list is near its 90-day low today. We re-check every morning.";

/** The latest price our daily poll recorded for a deal (real Keepa data). */
export type LatestPrice = {
  price_cents: number;
  currency: string;
  avg90_cents: number | null;
  pct_below_avg90: number | null;
  verdict?: string | null;
  observed_at: string;
};

export type FeaturedDeal = {
  offer_id: number;
  slug: string;
  title: string;
  brand: string | null;
  category: string | null;
  category_slug: string | null;
  merchant: string;
  price_cents: number;
  currency: string;
  product_url: string | null;
  price_checked: string | null;
  blurb: string | null;
  latest_price?: LatestPrice | null;
};

export type DealCategory = {
  name: string;
  slug: string;
  count: number;
};

type FeaturedDealsPayload = {
  count?: number;
  deals?: FeaturedDeal[];
};

type DealCategoriesPayload = {
  count?: number;
  categories?: DealCategory[];
};

// --- client (browser) — goes through the same-origin /api proxy ---------------

export async function requestFeaturedDeals(
  fetchImpl: typeof fetch = fetch
): Promise<FeaturedDeal[]> {
  try {
    const response = await fetchImpl("/api/featured-deals?limit=12", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return [];
    }
    const payload = (await response.json()) as FeaturedDealsPayload;
    return Array.isArray(payload.deals) ? payload.deals : [];
  } catch {
    return [];
  }
}

export async function requestDealCategories(
  fetchImpl: typeof fetch = fetch
): Promise<DealCategory[]> {
  try {
    const response = await fetchImpl("/api/featured-deals/categories", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return [];
    }
    const payload = (await response.json()) as DealCategoriesPayload;
    return Array.isArray(payload.categories) ? payload.categories : [];
  } catch {
    return [];
  }
}

// --- server — talks to the API directly, used by the SEO pages ---------------

async function apiJson<T>(path: string, revalidate = 3600): Promise<T | null> {
  try {
    const response = await fetch(new URL(path, getApiBaseUrl()), {
      headers: { Accept: "application/json" },
      next: { revalidate },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function fetchDeals(
  options: { category?: string; limit?: number } = {}
): Promise<FeaturedDeal[]> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 100) });
  if (options.category) {
    params.set("category", options.category);
  }
  const payload = await apiJson<FeaturedDealsPayload>(
    `/featured-deals?${params.toString()}`
  );
  return Array.isArray(payload?.deals) ? payload.deals : [];
}

export async function fetchDeal(slug: string): Promise<FeaturedDeal | null> {
  return apiJson<FeaturedDeal>(
    `/featured-deals/${encodeURIComponent(slug)}`
  );
}

export async function fetchPriceDrops(limit = 6): Promise<FeaturedDeal[]> {
  // Refreshed more often than the catalogue: the daily poll lands once a
  // morning and the section should pick it up within the half hour.
  const payload = await apiJson<FeaturedDealsPayload>(
    `/featured-deals/price-drops?limit=${limit}`,
    1800
  );
  return Array.isArray(payload?.deals) ? payload.deals : [];
}

export async function fetchDealCategories(): Promise<DealCategory[]> {
  const payload = await apiJson<DealCategoriesPayload>(
    "/featured-deals/categories"
  );
  return Array.isArray(payload?.categories) ? payload.categories : [];
}

// --- paths & formatting ------------------------------------------------------

export function dealPath(deal: Pick<FeaturedDeal, "slug">): string {
  return `/deal/${deal.slug}`;
}

export function categoryPath(slug: string): string {
  return `/category/${slug}`;
}

/**
 * Every featured deal is ingested with an affiliate link (the retailer URL plus
 * our tag), so we always route through /go with the affiliate target — that is
 * the hop that logs the click server-side and appends our SubID.
 */
export function featuredDealHref(deal: Pick<FeaturedDeal, "offer_id">): string {
  return `/go/${deal.offer_id}?t=affiliate`;
}

export function formatPriceCheckedDate(iso: string | null): string | null {
  if (!iso) {
    return null;
  }
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("en-CA", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

/** "Sep 28, 2026" for an ISO timestamp from the daily poll. */
export function formatObservedDate(iso: string | null | undefined): string | null {
  if (!iso) {
    return null;
  }
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("en-CA", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "America/Toronto",
  }).format(parsed);
}

/**
 * "12% below its 90-day average of $17.10" — or null when there is no average
 * or the price is not actually below it. Never phrased as a sale or discount.
 */
export function describeVsAverage(latest: LatestPrice): string | null {
  const pct = latest.pct_below_avg90;
  if (latest.avg90_cents === null || pct === null || pct <= 0) {
    return null;
  }
  return `${pct}% below its 90-day average of ${formatMoney(latest.avg90_cents, latest.currency)}`;
}

/**
 * The price to show for a deal: the latest one our daily check recorded when
 * there is one, otherwise the hand-checked snapshot. `checked` is its date.
 */
export function dealPriceNow(
  deal: Pick<FeaturedDeal, "price_cents" | "currency" | "price_checked" | "latest_price">
): { cents: number; currency: string; checked: string | null; daily: boolean } {
  const latest = deal.latest_price;
  if (latest) {
    return {
      cents: latest.price_cents,
      currency: latest.currency,
      checked: formatObservedDate(latest.observed_at),
      daily: true,
    };
  }
  return {
    cents: deal.price_cents,
    currency: deal.currency,
    checked: formatPriceCheckedDate(deal.price_checked),
    daily: false,
  };
}

export function formatMoney(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(
    cents / 100
  );
}
