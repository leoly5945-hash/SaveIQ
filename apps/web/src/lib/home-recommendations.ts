export const HOME_INTENT_PLACEHOLDER = "What are you looking for?";
export const HOME_AFFILIATE_DISCLOSURE =
  "Some links on this page are affiliate links. If you make a purchase through them, DealHunter may earn a commission at no extra cost to you.";

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
  if (offer.product_url) {
    return { href: offer.product_url, targetType: "product" };
  }
  if (offer.affiliate_url) {
    return { href: offer.affiliate_url, targetType: "affiliate" };
  }
  return null;
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

export function trackHomeDealClick(input: {
  offerId: number;
  targetType: ClickTargetType;
  anonymousUserId: string;
  fetchImpl?: typeof fetch;
}): void {
  const fetchImpl = input.fetchImpl ?? fetch;
  const referrer = typeof window === "undefined" ? undefined : window.location.href;
  void fetchImpl("/api/clicks", {
    body: JSON.stringify({
      offer_id: input.offerId,
      target_type: input.targetType,
      referrer,
      anonymous_user_id: input.anonymousUserId,
    }),
    headers: {
      Accept: "application/json",
      "content-type": "application/json",
    },
    keepalive: true,
    method: "POST",
  }).catch(() => {
    // Fire-and-forget: never block opening the deal URL.
  });
}
