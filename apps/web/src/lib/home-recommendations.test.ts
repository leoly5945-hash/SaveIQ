import { afterEach, describe, expect, it, vi } from "vitest";

import {
  dealLink,
  requestHomeRecommendations,
  trackHomeDealClick,
} from "./home-recommendations";

describe("requestHomeRecommendations", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts intent and anonymous_user_id in the JSON body", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          count: 1,
          recommendations: [
            {
              offer_id: 9,
              title: "Noise-cancelling headphones",
              offer_title: "Headphones deal",
              merchant: "Example Mart",
              price_cents: 12999,
              sale_price_cents: 9999,
              currency: "CAD",
              product_url: "https://example.test/deal",
              has_coupon: true,
              has_cashback: false,
            },
          ],
        }),
        { headers: { "content-type": "application/json" }, status: 200 }
      )
    );

    const result = await requestHomeRecommendations({
      intent: "wireless headphones",
      anonymousUserId: "anon_TestUserIdentifier",
      fetchImpl,
    });

    expect(result).toEqual({
      ok: true,
      offers: [
        expect.objectContaining({
          offer_id: 9,
          merchant: "Example Mart",
        }),
      ],
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/recommendations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          intent: "wireless headphones",
          limit: 5,
          market: "CA",
          anonymous_user_id: "anon_TestUserIdentifier",
        }),
      })
    );
    const headers = fetchImpl.mock.calls[0][1].headers as Record<string, string>;
    expect(headers["X-Anonymous-User-Id"]).toBeUndefined();
  });

  it("returns empty offers for a successful search with no matches", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ count: 0, recommendations: [] }), {
        headers: { "content-type": "application/json" },
        status: 200,
      })
    );

    await expect(
      requestHomeRecommendations({
        intent: "zzz no such deal",
        anonymousUserId: "anon_TestUserIdentifier",
        fetchImpl,
      })
    ).resolves.toEqual({ ok: true, offers: [] });
  });

  it("returns an error result when the API fails", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("nope", { status: 502 }));

    await expect(
      requestHomeRecommendations({
        intent: "wireless headphones",
        anonymousUserId: "anon_TestUserIdentifier",
        fetchImpl,
      })
    ).resolves.toEqual({ ok: false });
  });
});

describe("trackHomeDealClick", () => {
  it("fires /api/clicks without waiting for the response", () => {
    let resolveFetch: ((value: Response) => void) | undefined;
    const fetchImpl = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        })
    );

    const started = Date.now();
    trackHomeDealClick({
      offerId: 9,
      targetType: "product",
      anonymousUserId: "anon_TestUserIdentifier",
      fetchImpl,
    });
    const elapsed = Date.now() - started;

    expect(elapsed).toBeLessThan(50);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/clicks",
      expect.objectContaining({
        keepalive: true,
        method: "POST",
        body: JSON.stringify({
          offer_id: 9,
          target_type: "product",
          referrer: undefined,
          anonymous_user_id: "anon_TestUserIdentifier",
        }),
      })
    );
    resolveFetch?.(new Response("{}", { status: 201 }));
  });
});

describe("dealLink", () => {
  it("prefers product_url and product click type", () => {
    expect(
      dealLink({
        offer_id: 1,
        title: "Item",
        offer_title: "Item",
        merchant: "Shop",
        price_cents: 100,
        sale_price_cents: null,
        currency: "CAD",
        product_url: "https://example.test/p",
        affiliate_url: "https://example.test/a",
        has_coupon: false,
        has_cashback: false,
      })
    ).toEqual({ href: "https://example.test/p", targetType: "product" });
  });
});
