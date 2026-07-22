import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/clicks", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("proxies click tracking requests to the backend API", async () => {
    const requestBody = JSON.stringify({ offer_id: 1, target_type: "product" });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 1, target_type: "product" }), {
        headers: { "content-type": "application/json" },
        status: 201,
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/clicks", {
        body: requestBody,
        headers: {
          "content-type": "application/json",
          "user-agent": "vitest",
        },
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(201);
    expect(body.target_type).toBe("product");
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/clicks"),
      expect.objectContaining({
        body: requestBody,
        cache: "no-store",
        method: "POST",
      })
    );
  });
});
