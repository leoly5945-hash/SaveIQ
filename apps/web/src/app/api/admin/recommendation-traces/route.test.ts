import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/admin/recommendation-traces", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires an admin token", async () => {
    const response = await POST(
      new Request("https://web.test/api/admin/recommendation-traces", {
        body: JSON.stringify({ adminToken: "" }),
        method: "POST",
      })
    );

    expect(response.status).toBe(401);
  });

  it("proxies recommendation trace requests with the admin token header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          current_version_metadata: {
            fixture_set_version: "fixtures-v0",
            intent_parser_version: "intent-parser-v0",
            ranker_version: "ranker-v0",
            rule_version: "ruleset-2026-07-27-gate-4o",
            strategy: "rule_based_mock_v0",
          },
          recent_traces: [
            {
              created_at: "2026-07-27T00:00:00Z",
              evaluation_trace: [],
              fixture_set_version: "fixtures-v0",
              id: 42,
              intent_parser_version: "intent-parser-v0",
              parsed_intent: { search_query: "buds", sort: "lowest_price" },
              ranker_version: "ranker-v0",
              raw_intent: "buds",
              recommended_offer_ids: [1],
              result_count: 1,
              rule_version: "ruleset-2026-07-27-gate-4o",
              strategy: "rule_based_mock_v0",
            },
          ],
          total_traces: 1,
        }),
        {
          headers: { "content-type": "application/json" },
          status: 200,
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/admin/recommendation-traces", {
        body: JSON.stringify({ adminToken: "secret" }),
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.total_traces).toBe(1);
    expect(body.recent_traces[0].rule_version).toBe(
      "ruleset-2026-07-27-gate-4o"
    );
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/admin/affiliate/recommendation-traces"),
      expect.objectContaining({
        cache: "no-store",
        headers: expect.objectContaining({ "X-Admin-Token": "secret" }),
      })
    );
  });
});
