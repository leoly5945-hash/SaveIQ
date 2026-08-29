import { afterEach, describe, expect, it, vi } from "vitest";

import {
  dealLink,
  requestHomeRecommendations,
  withAnonymousId,
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

describe("dealLink", () => {
  const base = {
    offer_id: 1,
    title: "Item",
    offer_title: "Item",
    merchant: "Shop",
    price_cents: 100,
    sale_price_cents: null,
    currency: "CAD",
    has_coupon: false,
    has_cashback: false,
  };

  it("routes through /go with the product target when a product_url exists", () => {
    expect(
      dealLink({
        ...base,
        product_url: "https://example.test/p",
        affiliate_url: "https://example.test/a",
      })
    ).toEqual({ href: "/go/1?t=product", targetType: "product" });
  });

  it("falls back to the affiliate target when only affiliate_url exists", () => {
    expect(
      dealLink({ ...base, product_url: null, affiliate_url: "https://example.test/a" })
    ).toEqual({ href: "/go/1?t=affiliate", targetType: "affiliate" });
  });

  it("returns null when the offer has no destination", () => {
    expect(dealLink({ ...base, product_url: null })).toBeNull();
  });
});

describe("withAnonymousId", () => {
  it("appends aid to a href that already has a query string", () => {
    expect(withAnonymousId("/go/1?t=product", "anon_TestUserIdentifier")).toBe(
      "/go/1?t=product&aid=anon_TestUserIdentifier"
    );
  });

  it("returns the href unchanged when there is no anonymous id", () => {
    expect(withAnonymousId("/go/1?t=product", "")).toBe("/go/1?t=product");
  });
});
