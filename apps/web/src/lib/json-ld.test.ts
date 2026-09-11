import { describe, expect, it } from "vitest";

import { safeJsonLd } from "./json-ld";

describe("safeJsonLd", () => {
  it("escapes a literal </script> so it can't close the tag early", () => {
    // A malicious Amazon listing title, say — attacker-influenceable data
    // that ends up embedded in the JSON-LD <script> tag.
    const out = safeJsonLd({ name: "</script><script>alert(1)</script>" });
    expect(out).not.toContain("</script>");
    expect(out).not.toContain("<script>");
    expect(out).toContain("\\u003c/script>");
    // still valid JSON with the original value once parsed
    expect(JSON.parse(out)).toEqual({
      name: "</script><script>alert(1)</script>",
    });
  });

  it("round-trips ordinary data unchanged", () => {
    const data = { a: 1, b: "hello", c: [1, 2, 3] };
    expect(JSON.parse(safeJsonLd(data))).toEqual(data);
  });
});
