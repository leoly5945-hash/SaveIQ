import { describe, expect, it, vi } from "vitest";

import {
  featuredDealHref,
  formatPriceCheckedDate,
  requestFeaturedDeals,
  type FeaturedDeal,
} from "./featured-deals";

const SAMPLE: FeaturedDeal = {
  offer_id: 42,
  title: "Anker USB-C to USB-C Cable, 60W, 6 ft",
  brand: "Anker",
  category: "Electronics",
  merchant: "Amazon.ca",
  price_cents: 1699,
  currency: "CAD",
  product_url: "https://www.amazon.ca/dp/B088NRLMPV",
  price_checked: "2026-08-29",
  blurb: "Nylon-braided 60W USB-C charging cable.",
};

describe("requestFeaturedDeals", () => {
  it("returns the deals array from the API payload", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ count: 1, deals: [SAMPLE] }), {
          status: 200,
        })
      );

    await expect(requestFeaturedDeals(fetchImpl)).resolves.toEqual([SAMPLE]);
    expect(fetchImpl).toHaveBeenCalledWith("/api/featured-deals", {
      headers: { Accept: "application/json" },
    });
  });

  it("returns [] on a non-OK response", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response("nope", { status: 502 }));
    await expect(requestFeaturedDeals(fetchImpl)).resolves.toEqual([]);
  });

  it("returns [] when fetch throws", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("offline"));
    await expect(requestFeaturedDeals(fetchImpl)).resolves.toEqual([]);
  });
});

describe("featuredDealHref", () => {
  it("routes through /go with the affiliate target so the tag is applied", () => {
    expect(featuredDealHref(SAMPLE)).toBe("/go/42?t=affiliate");
  });
});

describe("formatPriceCheckedDate", () => {
  it("formats an ISO date", () => {
    expect(formatPriceCheckedDate("2026-08-29")).toBe("Aug 29, 2026");
  });

  it("returns null for missing or invalid input", () => {
    expect(formatPriceCheckedDate(null)).toBeNull();
    expect(formatPriceCheckedDate("not-a-date")).toBeNull();
  });
});
