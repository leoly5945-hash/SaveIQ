import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import AboutPage from "./page";

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

describe("AboutPage", () => {
  it("states who runs SaveIQ, how it earns, and the honesty rules", () => {
    const text = collectText(AboutPage()).replace(/\s+/g, " ");

    expect(text).toContain("Nextwave Software Company");
    expect(text).toContain("Vancouver, BC, Canada");
    expect(text).toContain("Leo Do");
    expect(text).toContain("leoly5945@gmail.com");
    expect(text).toContain("Amazon Associate");
    expect(text).toContain("never add a markup");
    expect(text).toContain("checked by hand");
    expect(text).not.toContain("undefined");
  });
});
