import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/admin/sync-mock", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires an admin token", async () => {
    const response = await POST(
      new Request("https://web.test/api/admin/sync-mock", {
        body: JSON.stringify({ adminToken: "" }),
        method: "POST",
      })
    );

    expect(response.status).toBe(401);
  });

  it("proxies mock sync requests with the admin token header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "completed_with_errors" }), {
        headers: { "content-type": "application/json" },
        status: 200,
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/admin/sync-mock", {
        body: JSON.stringify({ adminToken: "secret" }),
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.status).toBe("completed_with_errors");
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/admin/affiliate/sync/mock"),
      expect.objectContaining({
        cache: "no-store",
        headers: expect.objectContaining({ "X-Admin-Token": "secret" }),
        method: "POST",
      })
    );
  });
});
