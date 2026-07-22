import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/admin/staging-summary", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires an admin token", async () => {
    const response = await POST(
      new Request("https://web.test/api/admin/staging-summary", {
        body: JSON.stringify({ adminToken: "" }),
        method: "POST",
      })
    );

    expect(response.status).toBe(401);
  });

  it("proxies staging summary requests with the admin token header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ counts: { offers: 6 } }), {
        headers: { "content-type": "application/json" },
        status: 200,
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/admin/staging-summary", {
        body: JSON.stringify({ adminToken: "secret" }),
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.counts.offers).toBe(6);
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/admin/affiliate/staging-summary"),
      expect.objectContaining({
        cache: "no-store",
        headers: expect.objectContaining({ "X-Admin-Token": "secret" }),
      })
    );
  });
});
