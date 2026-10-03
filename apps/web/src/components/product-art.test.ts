import { describe, expect, it } from "vitest";

import { artKeyFor } from "./product-art";

describe("artKeyFor", () => {
  it("draws the kind of product named in the title", () => {
    expect(artKeyFor("Sony MDRZX110 Over-Ear Headphones (Black)", "electronics")).toBe("headphones");
    expect(artKeyFor("Lodge 8-Inch Pre-Seasoned Cast-Iron Skillet", "kitchen")).toBe("pan");
    expect(artKeyFor("Stanley PowerLock II Tape Measure, 25 ft", "tools")).toBe("wrench");
    expect(artKeyFor("Scotch Packing Tape Heavy Duty Shipping Tape", "office")).toBe("tape");
    expect(artKeyFor("Energizer AA Batteries, Max Double A Battery Alkaline", "electronics")).toBe(
      "battery"
    );
    expect(artKeyFor("KONG Classic Dog Toy", "pet-supplies")).toBe("bone");
  });

  it("falls back to the category, then to a plain box", () => {
    expect(artKeyFor("OXO Good Grips Swivel Peeler", "kitchen")).toBe("pot");
    expect(artKeyFor(null, "toys-games")).toBe("gamepad");
    expect(artKeyFor("Something unusual", null)).toBe("box");
  });

  it("does not match words inside other words", () => {
    expect(artKeyFor("Lightweight carpet cleaner refill", null)).toBe("box");
  });
});
