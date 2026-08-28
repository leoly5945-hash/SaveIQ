import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import TermsPage from "./page";

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

describe("Terms", () => {
  it("renders the terms of use", () => {
    const text = collectText(TermsPage()).replace(/\s+/g, " ");

    expect(text).toContain("Last updated");
    expect(text).toContain("Nextwave Software Company");
    expect(text).toContain("Before you buy, check the details");
    expect(text).toContain("is not a store and does not sell anything");
    expect(text).toContain("affiliate links");
    expect(text).toContain("British Columbia");
    expect(text).toContain("leoly5945@gmail.com");
  });
});
