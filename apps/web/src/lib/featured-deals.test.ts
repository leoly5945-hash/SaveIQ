import { describe, expect, it, vi } from "vitest";

import {
  categoryPath,
  dealPath,
  featuredDealHref,
  formatMoney,
  formatPriceCheckedDate,
  requestFeaturedDeals,
  type FeaturedDeal,
} from "./featured-deals";

const SAMPLE: FeaturedDeal = {
  offer_id: 42,
  slug: "anker-usb-c-to-usb-c-cable-60w-6-ft",
  title: "Anker USB-C to USB-C Cable, 60W, 6 ft",
  brand: "Anker",
  category: "Electronics",
  category_slug: "electronics",
  merchant: "Amazon.ca",
  price_cents: 1699,
  currency: "CAD",
  product_url: "https://www.amazon.ca/dp/B088NRLMPV",
  price_checked: "2026-08-29",
  blurb: "Nylon-braided 60W USB-C charging cable.",
};

describe("requestFeaturedDeals", () => {
  it("requests a capped homepage strip and returns the deals array", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ count: 1, deals: [SAMPLE] }), {
          status: 200,
        })
      );

    await expect(requestFeaturedDeals(fetchImpl)).resolves.toEqual([SAMPLE]);
    expect(fetchImpl).toHaveBeenCalledWith("/api/featured-deals?limit=12", {
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

describe("paths", () => {
  it("dealPath uses the slug", () => {
    expect(dealPath(SAMPLE)).toBe("/deal/anker-usb-c-to-usb-c-cable-60w-6-ft");
  });

  it("categoryPath uses the slug", () => {
    expect(categoryPath("electronics")).toBe("/category/electronics");
  });

  it("featuredDealHref routes through /go with the affiliate target", () => {
    expect(featuredDealHref(SAMPLE)).toBe("/go/42?t=affiliate");
  });
});

describe("formatting", () => {
  it("formatMoney renders CAD", () => {
    expect(formatMoney(1699, "CAD")).toBe("$16.99");
  });

  it("formatPriceCheckedDate formats an ISO date", () => {
    expect(formatPriceCheckedDate("2026-08-29")).toBe("Aug 29, 2026");
  });

  it("formatPriceCheckedDate returns null for missing or invalid input", () => {
    expect(formatPriceCheckedDate(null)).toBeNull();
    expect(formatPriceCheckedDate("not-a-date")).toBeNull();
  });
});
