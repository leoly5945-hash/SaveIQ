import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/admin/recommendation-evaluation", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires an admin token", async () => {
    const response = await POST(
      new Request("https://web.test/api/admin/recommendation-evaluation", {
        body: JSON.stringify({ adminToken: "" }),
        method: "POST",
      })
    );

    expect(response.status).toBe(401);
  });

  it("proxies recommendation evaluation requests with the admin token header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          case_count: 1,
          cases: [],
          failed_count: 0,
          fixture_set_version: "fixtures-v0",
          intent_parser_version: "intent-parser-v0",
          passed_count: 1,
          ranker_version: "ranker-v0",
          rule_version: "ruleset-2026-07-27-gate-4o",
          status: "ok",
          strategy: "rule_based_mock_v0",
        }),
        {
          headers: { "content-type": "application/json" },
          status: 200,
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/admin/recommendation-evaluation", {
        body: JSON.stringify({ adminToken: "secret" }),
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.status).toBe("ok");
    expect(body.rule_version).toBe("ruleset-2026-07-27-gate-4o");
    expect(fetchMock).toHaveBeenCalledWith(
      new URL(
        "http://localhost:8000/admin/affiliate/recommendation-evaluation"
      ),
      expect.objectContaining({
        cache: "no-store",
        headers: expect.objectContaining({ "X-Admin-Token": "secret" }),
      })
    );
  });
});
