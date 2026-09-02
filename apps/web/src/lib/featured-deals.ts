import { getApiBaseUrl } from "@/lib/config";

export const FEATURED_DEALS_HEADING = "Featured deals";
export const FEATURED_DEALS_BLURB =
  "A small set of real products we price-checked by hand. Prices are a snapshot from the date shown — always confirm the current price at the retailer before you buy.";
export const AMAZON_ASSOCIATE_DISCLOSURE =
  "As an Amazon Associate, SaveIQ earns from qualifying purchases.";

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

// --- server — talks to the API directly, used by the SEO pages ---------------

async function apiJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(new URL(path, getApiBaseUrl()), {
      headers: { Accept: "application/json" },
      next: { revalidate: 3600 },
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

export function formatMoney(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(
    cents / 100
  );
}
