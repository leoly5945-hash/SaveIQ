import { describe, expect, it } from "vitest";

import { buyLinkRel } from "./config";

describe("buyLinkRel", () => {
  it("lets our own hop see the page the click came from", () => {
    expect(buyLinkRel("/go/amazon/B004VBC0FM?src=check")).toBe("sponsored nofollow noopener");
    expect(buyLinkRel("/go/12?t=affiliate")).toBe("sponsored nofollow noopener");
  });

  it("keeps noreferrer on links that leave the site directly", () => {
    expect(buyLinkRel("https://www.amazon.ca/dp/B004VBC0FM?tag=saveiq-20")).toContain("noreferrer");
    expect(buyLinkRel(null)).toContain("noreferrer");
  });
});
