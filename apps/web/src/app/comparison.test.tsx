import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import type { Comparison, MerchantOffer } from "@/lib/price-check";

import { ComparisonBlock } from "./comparison";

function collectText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(collectText).join(" ");
  }
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return collectText(node.props.children);
  }
  return "";
}

function offer(merchant: string, price_cents: number, confidence = 0.7): MerchantOffer {
  return { merchant, price_cents, currency: "CAD", url: `https://example.test/${merchant}`, match_confidence: confidence };
}

const BASE: Comparison = {
  reference_merchant: "Amazon.ca",
  reference_price_cents: 99999,
  currency: "CAD",
  offers: [],
  cheapest: null,
};

describe("ComparisonBlock", () => {
  it("renders nothing with no offers", () => {
    expect(ComparisonBlock({ comparison: { ...BASE, offers: [] } })).toBeNull();
    expect(ComparisonBlock({ comparison: null })).toBeNull();
  });

  it("leads with the confirmed cheapest merchant when one clears the bar", () => {
    const cheapest = offer("Best Buy Canada Marketplace", 45999, 0.72);
    const text = collectText(
      ComparisonBlock({
        comparison: { ...BASE, offers: [cheapest], cheapest },
      })
    );
    expect(text).toContain("Cheaper at");
    expect(text).toContain("Best Buy Canada Marketplace");
  });

  it("does not claim Amazon has the best price when an unconfirmed offer is actually lower", () => {
    // This is the bug: Walmart.ca genuinely undercuts Amazon here, but its
    // match confidence didn't clear the bar, so `cheapest` stays null.
    const walmart = offer("Walmart.ca", 45999, 0.64);
    const text = collectText(
      ComparisonBlock({
        comparison: { ...BASE, offers: [walmart], cheapest: null },
      })
    );
    expect(text).not.toContain("Amazon.ca has the best price");
    expect(text).toContain("couldn't confidently match");
  });

  it("says Amazon has the best price only when nothing is actually cheaper", () => {
    const pricier = offer("Some Reseller", 150000, 0.8);
    const text = collectText(
      ComparisonBlock({
        comparison: { ...BASE, offers: [pricier], cheapest: null },
      })
    );
    expect(text).toContain("Amazon.ca has the best price");
  });
});
