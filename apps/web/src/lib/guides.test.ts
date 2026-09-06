import { describe, expect, it } from "vitest";

import { GUIDES, getGuide, guidePath, guidesForCategory } from "./guides";

describe("GUIDES", () => {
  it("has 5-8 guides with unique slugs", () => {
    expect(GUIDES.length).toBeGreaterThanOrEqual(5);
    expect(GUIDES.length).toBeLessThanOrEqual(8);
    const slugs = GUIDES.map((g) => g.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it("every guide has real content", () => {
    for (const g of GUIDES) {
      expect(g.slug).toMatch(/^[a-z0-9-]+$/);
      expect(g.title.length).toBeGreaterThan(10);
      expect(g.description.length).toBeGreaterThan(20);
      expect(g.updated).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(g.readMinutes).toBeGreaterThan(0);
      expect(g.intro.length).toBeGreaterThan(0);
      expect(g.sections.length).toBeGreaterThanOrEqual(3);
      for (const s of g.sections) {
        expect(s.heading.length).toBeGreaterThan(3);
        expect(s.body.length).toBeGreaterThan(0);
        expect(s.body.every((p) => p.length > 40)).toBe(true);
      }
    }
  });
});

describe("helpers", () => {
  it("getGuide resolves by slug", () => {
    const g = GUIDES[0];
    expect(getGuide(g.slug)).toBe(g);
    expect(getGuide("nope")).toBeUndefined();
  });

  it("guidePath builds the URL", () => {
    expect(guidePath("x-y")).toBe("/guide/x-y");
  });

  it("guidesForCategory filters by relatedCategories", () => {
    const elec = guidesForCategory("electronics");
    expect(elec.length).toBeGreaterThan(0);
    expect(elec.every((g) => g.relatedCategories?.includes("electronics"))).toBe(
      true
    );
    expect(guidesForCategory("does-not-exist")).toEqual([]);
  });
});
