import { describe, expect, it } from "vitest";

import {
  type CheckResult,
  formatMoney,
  looksSubmittable,
  ninetyDayBand,
  normalizeResult,
  VERDICT_COPY,
  type PriceIntelligence,
} from "./price-check";

describe("looksSubmittable", () => {
  it("accepts amazon links and bare ASINs", () => {
    expect(looksSubmittable("https://www.amazon.ca/dp/B09VPHVT9Z")).toBe(true);
    expect(looksSubmittable("amazon.ca/Anker-737/dp/B09VPHVT9Z/ref=x")).toBe(true);
    expect(looksSubmittable("https://amzn.to/3abcXYZ")).toBe(true);
    expect(looksSubmittable("B09VPHVT9Z")).toBe(true);
    expect(looksSubmittable("  b09vphvt9z  ")).toBe(true);
  });

  it("rejects anything else", () => {
    expect(looksSubmittable("hello world")).toBe(false);
    expect(looksSubmittable("https://www.walmart.ca/en/ip/thing")).toBe(false);
    expect(looksSubmittable("")).toBe(false);
  });
});

describe("ninetyDayBand", () => {
  const intel = (over: Partial<PriceIntelligence> = {}): PriceIntelligence => ({
    currency: "CAD",
    series_kind: "amazon",
    total_points: 90,
    coverage_days: 90,
    current_cents: 2131,
    windows: {
      "90": {
        days: 90,
        sample_count: 90,
        min_cents: 1899,
        max_cents: 2131,
        avg_cents: 1917,
        median_cents: 1899,
      },
    },
    all_time_min_cents: 999,
    all_time_max_cents: 2154,
    current_percentile_90d: 0.92,
    is_all_time_low: false,
    source_observations: 1,
    lifetime_observations: 412,
    provider_stats: { avg90_cents: 1914 },
    ...over,
  });

  it("takes min/max from the window and avg from provider stats", () => {
    expect(ninetyDayBand(intel())).toEqual({ min: 1899, max: 2131, avg: 1914 });
  });

  it("falls back to the window avg without provider stats", () => {
    expect(ninetyDayBand(intel({ provider_stats: {} }))).toEqual({
      min: 1899,
      max: 2131,
      avg: 1917,
    });
  });
});

describe("presentation", () => {
  it("formatMoney handles null", () => {
    expect(formatMoney(null, "CAD")).toBe("—");
    expect(formatMoney(2131, "CAD")).toContain("21.31");
  });

  it("every verdict has copy", () => {
    for (const key of ["BUY", "WAIT", "FAIR", "UNKNOWN"] as const) {
      expect(VERDICT_COPY[key].label.length).toBeGreaterThan(0);
      expect(VERDICT_COPY[key].blurb.length).toBeGreaterThan(0);
    }
  });
});

describe("normalizeResult", () => {
  const base = {
    provider: "keepa",
    provider_product_id: "B0TEST00001",
    title: "Test",
    product_url: "https://www.amazon.ca/dp/B0TEST00001",
    currency: "CAD",
    assessment: { effective_price: { currency: "CAD" } },
  } as unknown as CheckResult;

  it("keeps the tagged buy_url from the API", () => {
    const tagged = "https://www.amazon.ca/dp/B0TEST00001?tag=saveiq-20&ascsubtag=check";
    expect(normalizeResult({ ...base, buy_url: tagged }).buy_url).toBe(tagged);
  });

  it("falls back to product_url when the API omits buy_url", () => {
    expect(normalizeResult({ ...base, buy_url: null }).buy_url).toBe(
      "https://www.amazon.ca/dp/B0TEST00001"
    );
  });
});
