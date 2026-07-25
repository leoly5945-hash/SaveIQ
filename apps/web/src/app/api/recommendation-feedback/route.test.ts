import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/recommendation-feedback", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("proxies recommendation feedback to the backend API", async () => {
    const requestBody = JSON.stringify({
      offer_id: 1,
      rating: "helpful",
      trace_event_id: 7,
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 1,
          offer_id: 1,
          rating: "helpful",
          trace_event_id: 7,
        }),
        {
          headers: { "content-type": "application/json" },
          status: 201,
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/recommendation-feedback", {
        body: requestBody,
        headers: {
          "content-type": "application/json",
        },
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(201);
    expect(body.rating).toBe("helpful");
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/recommendations/feedback"),
      expect.objectContaining({
        body: requestBody,
        cache: "no-store",
        method: "POST",
      })
    );
  });
});
