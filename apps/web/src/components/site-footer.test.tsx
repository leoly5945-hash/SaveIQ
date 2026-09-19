import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { HOME_AFFILIATE_DISCLOSURE } from "@/lib/home-recommendations";

import { SiteFooter } from "./site-footer";

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

describe("SiteFooter", () => {
  it("shows operator identity, disclosure and the trust pages on every page", () => {
    const text = collectText(SiteFooter()).replace(/\s+/g, " ");

    expect(text).toContain("Nextwave Software Company");
    expect(text).toContain("Leo Do");
    expect(text).toContain(HOME_AFFILIATE_DISCLOSURE);
    expect(text).toContain("Editorial Guidelines");
    expect(text).toContain("Affiliate Disclosure");
    expect(text).toContain("Privacy");
    expect(text).toContain("Terms");
  });
});
