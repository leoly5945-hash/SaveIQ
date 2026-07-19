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
  it("renders foundation status", () => {
    const text = collectText(Home()).replace(/\s+/g, " ");

    expect(text).toContain("DealHunter foundation");
    expect(text).toContain("Mock interface only");
  });
});
