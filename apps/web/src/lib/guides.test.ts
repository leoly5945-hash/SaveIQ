import { describe, expect, it } from "vitest";

import { GUIDES, getGuide, guidePath, guidesForCategory } from "./guides";

describe("GUIDES", () => {
  it("has 5-16 guides with unique slugs", () => {
    expect(GUIDES.length).toBeGreaterThanOrEqual(5);
    expect(GUIDES.length).toBeLessThanOrEqual(16);
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

describe("sourced guides", () => {
  it("tables are rectangular and checked guides cite https sources", () => {
    for (const g of GUIDES) {
      for (const s of g.sections) {
        if (s.table) {
          expect(s.table.caption.length).toBeGreaterThan(10);
          for (const row of s.table.rows) {
            expect(row.length).toBe(s.table.headers.length);
          }
        }
      }
      if (g.checked) {
        expect(g.checked).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        expect(g.sources?.length ?? 0).toBeGreaterThan(0);
      }
      for (const src of g.sources ?? []) {
        expect(src.url).toMatch(/^https:\/\//);
        expect(src.label.length).toBeGreaterThan(10);
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
