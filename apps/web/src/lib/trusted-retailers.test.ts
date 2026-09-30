import { describe, expect, it } from "vitest";

import { isTrustedRetailer } from "./trusted-retailers";

describe("isTrustedRetailer", () => {
  it("accepts big Canadian retailers however Google Shopping spells them", () => {
    for (const name of [
      "Best Buy",
      "BestBuy.ca",
      "Best Buy Canada",
      "Walmart.ca",
      "Canadian Tire",
      "Staples.ca",
      "Home Depot Canada",
      "Lowe's",
      "Hudson's Bay",
      "Apple Store",
      "Samsung Canada",
      "Canada Computers",
    ]) {
      expect(isTrustedRetailer(name), name).toBe(true);
    }
  });

  it("does not vouch for stores shoppers may not know", () => {
    for (const name of ["Vuugo", "Monsieur Balayeuse", "tvoutlet.ca", "Snapklik.com", "Techinn.com", "Shopper Deals", null]) {
      expect(isTrustedRetailer(name), String(name)).toBe(false);
    }
  });
});
