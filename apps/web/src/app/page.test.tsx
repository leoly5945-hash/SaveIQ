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
    expect(text).toContain("Stop overpaying.");
    expect(text).toContain("Know the real lowest price.");
    expect(text).toContain("How SaveIQ works");
    expect(text).toContain(HOME_AFFILIATE_DISCLOSURE);
    expect(text).toContain("Privacy");
    expect(text).not.toContain("Staging mock data only");
    expect(text).not.toContain("Admin token");
  });
});
