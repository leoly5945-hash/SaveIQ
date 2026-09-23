import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import Home from "./page";

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

describe("Home", () => {
  it("renders the public search shell", () => {
    const text = collectText(Home()).replace(/\s+/g, " ");

    expect(text).toContain("SaveIQ");
    expect(text).toContain("Independent buying guides");
    expect(text).toContain("Shopping intelligence");
    expect(text).toContain("at its smartest.");
    expect(text).toContain("Latest buying guides");
    expect(text).toContain("Check a price");
    // paste-a-link is still offered, just demoted below search
    expect(text).toContain("Already looking at something on Amazon.ca");
    expect(text).toContain("How we evaluate");
    expect(text).toContain("We don't lab-test products.");
    expect(text).toContain("Editorial Guidelines");
    expect(text).toContain("Affiliate Disclosure");
    expect(text).not.toContain("Staging mock data only");
    expect(text).not.toContain("Admin token");
    // No overclaims: the verdict is deterministic and merchant-blind.
    expect(text).not.toContain("AI Router");
    expect(text).not.toContain("stacks coupons and cashback");
    expect(text).toContain("No merchant pays for a better verdict");
  });
});
