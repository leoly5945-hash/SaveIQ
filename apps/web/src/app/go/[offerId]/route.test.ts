import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

function ctx(offerId: string) {
  return { params: Promise.resolve({ offerId }) };
}

describe("GET /go/[offerId]", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards click headers to the API and 302s to the API's Location", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 302,
        headers: { location: "https://retailer.test/p?subid=abc123" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new Request("https://saveiq.ca/go/7?t=product&aid=anon_TestUserIdentifier", {
        headers: {
          "user-agent": "Mozilla/5.0",
          referer: "https://saveiq.ca/",
          "sec-purpose": "prefetch;prerender",
        },
      }),
      ctx("7")
    );

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://retailer.test/p?subid=abc123");
    expect(response.headers.get("x-robots-tag")).toBe("noindex, nofollow");

    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toBe("http://localhost:8000/go/7?t=product&aid=anon_TestUserIdentifier");
    expect(init.redirect).toBe("manual");
    expect(init.headers["user-agent"]).toBe("Mozilla/5.0");
    expect(init.headers["sec-purpose"]).toBe("prefetch;prerender");
  });

  it("redirects home when the API has no destination", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not found", { status: 404 }))
    );
    const response = await GET(new Request("https://saveiq.ca/go/999"), ctx("999"));
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://saveiq.ca/");
  });

  it("redirects home when the API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("network down"))
    );
    const response = await GET(new Request("https://saveiq.ca/go/7"), ctx("7"));
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://saveiq.ca/");
  });
});
