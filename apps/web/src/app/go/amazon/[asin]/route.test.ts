import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

function ctx(asin: string) {
  return { params: Promise.resolve({ asin }) };
}

const PAGE = "https://www.saveiq.ca/check/B004VBC0FM";

describe("GET /go/amazon/[asin]", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks the API to log the click with the page it came from, then follows it to Amazon", async () => {
    const tagged = "https://www.amazon.ca/dp/B004VBC0FM?tag=saveiq-20&ascsubtag=check";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 302, headers: { location: tagged } }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new Request("https://www.saveiq.ca/go/amazon/b004vbc0fm?src=check", {
        headers: { "user-agent": "Mozilla/5.0", referer: PAGE, "cf-connecting-ip": "203.0.113.7" },
      }),
      ctx("b004vbc0fm")
    );

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(tagged);
    expect(response.headers.get("x-robots-tag")).toBe("noindex, nofollow");
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toBe("http://localhost:8000/go/amazon/B004VBC0FM?src=check");
    expect(init.headers.referer).toBe(PAGE);
    expect(init.headers["x-saveiq-client-ip"]).toBe("203.0.113.7");
  });

  it("still sends the shopper to the tagged Amazon page when the API is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));
    const response = await GET(
      new Request("https://www.saveiq.ca/go/amazon/B004VBC0FM?src=checkbox"),
      ctx("B004VBC0FM")
    );
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(
      "https://www.amazon.ca/dp/B004VBC0FM?tag=saveiq-20&ascsubtag=checkbox"
    );
  });

  it("never follows the API to a non-Amazon destination", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(null, { status: 302, headers: { location: "https://evil.example/x" } })
        )
    );
    const response = await GET(
      new Request("https://www.saveiq.ca/go/amazon/B004VBC0FM"),
      ctx("B004VBC0FM")
    );
    expect(response.headers.get("location")).toBe(
      "https://www.amazon.ca/dp/B004VBC0FM?tag=saveiq-20&ascsubtag=check"
    );
  });

  it("sends a malformed product id home instead of to Amazon", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const response = await GET(
      new Request("https://www.saveiq.ca/go/amazon/nope", { headers: { host: "www.saveiq.ca" } }),
      ctx("nope")
    );
    expect(response.headers.get("location")).toBe("https://www.saveiq.ca/");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
