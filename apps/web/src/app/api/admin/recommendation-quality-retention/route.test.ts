import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/admin/recommendation-quality-retention", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires an admin token", async () => {
    const response = await POST(
      new Request(
        "https://web.test/api/admin/recommendation-quality-retention",
        {
          body: JSON.stringify({ adminToken: "" }),
          method: "POST",
        }
      )
    );

    expect(response.status).toBe(401);
  });

  it("proxies retention dry run with the admin token header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          dry_run: true,
          feedback_events_deleted: 0,
          feedback_events_to_delete: 1,
          keep_latest_traces: 10,
          retained_trace_events: 10,
          total_feedback_before: 4,
          total_traces_before: 12,
          trace_events_deleted: 0,
          trace_events_to_delete: 2,
        }),
        {
          headers: { "content-type": "application/json" },
          status: 200,
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request(
        "https://web.test/api/admin/recommendation-quality-retention",
        {
          body: JSON.stringify({
            adminToken: "secret",
            dryRun: true,
            keepLatestTraces: 10,
          }),
          method: "POST",
        }
      )
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.trace_events_to_delete).toBe(2);
    expect(fetchMock).toHaveBeenCalledWith(
      new URL(
        "http://localhost:8000/admin/affiliate/recommendation-quality/retention"
      ),
      expect.objectContaining({
        body: JSON.stringify({
          dry_run: true,
          keep_latest_traces: 10,
        }),
        cache: "no-store",
        headers: expect.objectContaining({ "X-Admin-Token": "secret" }),
        method: "POST",
      })
    );
  });
});
