import { isValidElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "./page";

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

describe("Privacy", () => {
  it("renders a draft privacy policy", () => {
    const text = collectText(PrivacyPage()).replace(/\s+/g, " ");

    expect(text).toContain("Draft — pending legal review");
    expect(text).toContain("not final legal advice");
    expect(text).toContain("do not sell personal information");
    expect(text).toContain("Contact method TBD");
    expect(text).toContain("anonymous identifier");
  });
});
