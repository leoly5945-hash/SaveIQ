import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("GET /api/offers/[offerId]", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("proxies offer detail requests to the backend API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ offer_id: 1 }), {
        headers: { "content-type": "application/json" },
        status: 200,
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(new Request("https://web.test/api/offers/1"), {
      params: Promise.resolve({ offerId: "1" }),
    });
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.offer_id).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/search/offers/1"),
      expect.objectContaining({ cache: "no-store" })
    );
  });
});
