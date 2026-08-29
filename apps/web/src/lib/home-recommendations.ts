export const HOME_INTENT_PLACEHOLDER = "What are you looking for?";
export const HOME_AFFILIATE_DISCLOSURE =
  "Some links on this page are affiliate links. If you make a purchase through them, SaveIQ may earn a commission at no extra cost to you.";

export type ClickTargetType = "product" | "affiliate";

export type HomeOffer = {
  offer_id: number;
  title: string;
  offer_title: string;
  merchant: string;
  price_cents: number;
  sale_price_cents: number | null;
  currency: string;
  product_url: string | null;
  affiliate_url?: string | null;
  has_coupon: boolean;
  has_cashback: boolean;
};

type RecommendationPayload = {
  count?: number;
  recommendations?: HomeOffer[];
};

export type HomeRecommendationsResult =
  | { ok: true; offers: HomeOffer[] }
  | { ok: false };

export function formatMoney(cents: number, currency: string) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
  }).format(cents / 100);
}

export function dealLink(
  offer: HomeOffer
): { href: string; targetType: ClickTargetType } | null {
  let targetType: ClickTargetType | null = null;
  if (offer.product_url) {
    targetType = "product";
  } else if (offer.affiliate_url) {
    targetType = "affiliate";
  }
  if (!targetType) {
    return null;
  }
  // Route through our first-party /go redirect so the click is logged
  // server-side and the outbound URL gets our SubID for reconciliation.
  return { href: `/go/${offer.offer_id}?t=${targetType}`, targetType };
}

export async function requestHomeRecommendations(input: {
  intent: string;
  anonymousUserId: string;
  fetchImpl?: typeof fetch;
}): Promise<HomeRecommendationsResult> {
  const intent = input.intent.trim().slice(0, 240);
  if (intent.length < 3) {
    return { ok: false };
  }
  const fetchImpl = input.fetchImpl ?? fetch;
  try {
    const response = await fetchImpl("/api/recommendations", {
      body: JSON.stringify({
        intent,
        limit: 5,
        market: "CA",
        anonymous_user_id: input.anonymousUserId,
      }),
      headers: {
        Accept: "application/json",
        "content-type": "application/json",
      },
      method: "POST",
    });
    if (!response.ok) {
      return { ok: false };
    }
    const payload = (await response.json()) as RecommendationPayload;
    const offers = Array.isArray(payload.recommendations)
      ? payload.recommendations
      : [];
    return { ok: true, offers };
  } catch {
    return { ok: false };
  }
}

/** Append the anonymous id so the /go redirect can attribute the click. */
export function withAnonymousId(href: string, anonymousUserId: string): string {
  if (!anonymousUserId) {
    return href;
  }
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}aid=${encodeURIComponent(anonymousUserId)}`;
}
