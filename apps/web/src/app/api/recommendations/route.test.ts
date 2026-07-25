import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/recommendations", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("proxies recommendation requests to the backend API", async () => {
    const requestBody = JSON.stringify({
      intent: "fresh earbuds with coupon",
      limit: 2,
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          count: 1,
          strategy: "rule_based_mock_v0",
          recommendations: [],
          evaluation_trace: [],
        }),
        {
          headers: { "content-type": "application/json" },
          status: 200,
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/recommendations", {
        body: requestBody,
        headers: {
          "content-type": "application/json",
        },
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.strategy).toBe("rule_based_mock_v0");
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/recommendations"),
      expect.objectContaining({
        body: requestBody,
        cache: "no-store",
        method: "POST",
      })
    );
  });
});
