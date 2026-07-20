import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("GET /api/search", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("proxies search requests to the backend API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ query: "buds", count: 0, results: [] }), {
        headers: { "content-type": "application/json" },
        status: 200,
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new Request("https://web.test/api/search?q=buds")
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.query).toBe("buds");
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/search?q=buds"),
      expect.objectContaining({ cache: "no-store" })
    );
  });
});
