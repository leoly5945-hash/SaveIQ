import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import StagingTools from "./page";

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

describe("Staging tools", () => {
  it("renders the relocated mock search shell", () => {
    const text = collectText(StagingTools()).replace(/\s+/g, " ");

    expect(text).toContain("DealHunter");
    expect(text).toContain("Staging mock data only");
  });
});
