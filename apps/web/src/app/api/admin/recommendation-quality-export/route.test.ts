import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/admin/recommendation-quality-export", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires an admin token", async () => {
    const response = await POST(
      new Request("https://web.test/api/admin/recommendation-quality-export", {
        body: JSON.stringify({ adminToken: "" }),
        method: "POST",
      })
    );

    expect(response.status).toBe(401);
  });

  it("proxies quality export requests with the admin token header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          environment: "staging",
          recommendation_evaluation: { status: "ok" },
          report_version: "gate-4p-quality-export-v1",
          version_metadata: {
            fixture_set_version: "fixtures-v0",
            intent_parser_version: "intent-parser-v0",
            ranker_version: "ranker-v0",
            rule_version: "ruleset-2026-07-27-gate-4o",
            strategy: "rule_based_mock_v0",
          },
        }),
        {
          headers: { "content-type": "application/json" },
          status: 200,
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/admin/recommendation-quality-export", {
        body: JSON.stringify({ adminToken: "secret" }),
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.report_version).toBe("gate-4p-quality-export-v1");
    expect(body.version_metadata.rule_version).toBe(
      "ruleset-2026-07-27-gate-4o"
    );
    expect(fetchMock).toHaveBeenCalledWith(
      new URL(
        "http://localhost:8000/admin/affiliate/recommendation-quality/export"
      ),
      expect.objectContaining({
        cache: "no-store",
        headers: expect.objectContaining({ "X-Admin-Token": "secret" }),
      })
    );
  });
});
