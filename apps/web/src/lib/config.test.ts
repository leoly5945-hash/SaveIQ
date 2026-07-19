import { describe, expect, it } from "vitest";

import { getApiBaseUrl, getBrandName } from "./config";

describe("getApiBaseUrl", () => {
  it("returns a local default", () => {
    expect(getApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("returns the default brand name", () => {
    expect(getBrandName()).toBe("DealHunter");
  });
});
