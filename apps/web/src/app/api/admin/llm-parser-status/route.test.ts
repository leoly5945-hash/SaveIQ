import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

describe("POST /api/admin/llm-parser-status", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires an admin token", async () => {
    const response = await POST(
      new Request("https://web.test/api/admin/llm-parser-status", {
        body: JSON.stringify({ adminToken: "" }),
        method: "POST",
      })
    );

    expect(response.status).toBe(401);
  });

  it("proxies parser status requests with the admin token header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          active_parser_version: "intent-parser-v0",
          closeout_ready: true,
          fallback_parser_version: "intent-parser-v0",
          feature_enabled: false,
          guardrails: ["do not browse the web or call affiliate networks"],
          live_parser_ready: false,
          openai_configured: false,
          openai_intent_model: "gpt-4.1-mini",
          parser_mode: "disabled",
          required_enablement: [],
          staging_default_safe: true,
          timeout_seconds: 10,
        }),
        {
          headers: { "content-type": "application/json" },
          status: 200,
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("https://web.test/api/admin/llm-parser-status", {
        body: JSON.stringify({ adminToken: "secret" }),
        method: "POST",
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.active_parser_version).toBe("intent-parser-v0");
    expect(body.closeout_ready).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/admin/affiliate/llm-parser-status"),
      expect.objectContaining({
        cache: "no-store",
        headers: expect.objectContaining({ "X-Admin-Token": "secret" }),
      })
    );
  });
});
