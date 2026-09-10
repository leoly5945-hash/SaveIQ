import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { HOME_AFFILIATE_DISCLOSURE } from "@/lib/home-recommendations";

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
    expect(text).toContain("What are you thinking of buying?");
    expect(text).toContain("We'll tell you: buy now, or wait.");
    // paste-a-link is still offered, just demoted below search
    expect(text).toContain("Already looking at something on Amazon.ca");
    expect(text).toContain("How the check works");
    expect(text).toContain(HOME_AFFILIATE_DISCLOSURE);
    expect(text).toContain("Privacy");
    expect(text).not.toContain("Staging mock data only");
    expect(text).not.toContain("Admin token");
    // No overclaims: the verdict is deterministic and merchant-blind.
    expect(text).not.toContain("AI Router");
    expect(text).not.toContain("stacks coupons and cashback");
    expect(text).toContain("No merchant pays for a better verdict");
  });
});
