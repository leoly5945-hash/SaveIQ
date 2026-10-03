import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { SiteHeader } from "./site-header";

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

describe("SiteHeader", () => {
  it("shows the brand, tagline and main navigation on every page", () => {
    const text = collectText(SiteHeader()).replace(/\s+/g, " ");

    expect(text).toContain("SaveIQ");
    expect(text).toContain("Smarter Shopping in Canada");
    expect(text).toContain("Price Check");
    expect(text).toContain("Price Watch");
    expect(text).toContain("Buying Guides");
    // No accounts exist, so the header must not offer a sign-in.
    expect(text).not.toContain("Sign in");
  });
});
