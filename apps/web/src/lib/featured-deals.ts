export const FEATURED_DEALS_HEADING = "Featured deals";
export const FEATURED_DEALS_BLURB =
  "A small set of real products we price-checked by hand. Prices are a snapshot from the date shown — always confirm the current price at the retailer before you buy.";
export const AMAZON_ASSOCIATE_DISCLOSURE =
  "As an Amazon Associate, SaveIQ earns from qualifying purchases.";

export type FeaturedDeal = {
  offer_id: number;
  title: string;
  brand: string | null;
  category: string | null;
  merchant: string;
  price_cents: number;
  currency: string;
  product_url: string | null;
  price_checked: string | null;
  blurb: string | null;
};

type FeaturedDealsPayload = {
  count?: number;
  deals?: FeaturedDeal[];
};

export async function requestFeaturedDeals(
  fetchImpl: typeof fetch = fetch
): Promise<FeaturedDeal[]> {
  try {
    const response = await fetchImpl("/api/featured-deals", {
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

/**
 * Every featured deal is ingested with an affiliate link (the retailer URL plus
 * our tag), so we always route through /go with the affiliate target — that is
 * the hop that logs the click server-side and appends our SubID.
 */
export function featuredDealHref(deal: FeaturedDeal): string {
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
