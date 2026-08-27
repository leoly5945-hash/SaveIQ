import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { proxy } from "./proxy";

const ORIGINAL_ENV = { ...process.env };

function request(path: string, authorization?: string): NextRequest {
  const headers = new Headers();
  if (authorization) {
    headers.set("authorization", authorization);
  }
  return new NextRequest(`https://www.saveiq.ca${path}`, { headers });
}

describe("proxy", () => {
  beforeEach(() => {
    process.env = { ...ORIGINAL_ENV };
  });

  afterEach(() => {
    process.env = { ...ORIGINAL_ENV };
  });

  describe("noindex header", () => {
    it("sets X-Robots-Tag when PRODUCTION_NOINDEX is true", () => {
      process.env.PRODUCTION_NOINDEX = "true";
      delete process.env.STAGING_NOINDEX;

      const response = proxy(request("/"));
      expect(response.headers.get("X-Robots-Tag")).toBe("noindex, nofollow");
    });

    it("does not set X-Robots-Tag when neither flag is true", () => {
      delete process.env.PRODUCTION_NOINDEX;
      delete process.env.STAGING_NOINDEX;

      const response = proxy(request("/"));
      expect(response.headers.get("X-Robots-Tag")).toBeNull();
    });
  });

  describe("/internal/* guard", () => {
    it("404s when INTERNAL_TOOLS_USER/PASSWORD are not configured", () => {
      delete process.env.INTERNAL_TOOLS_USER;
      delete process.env.INTERNAL_TOOLS_PASSWORD;

      const response = proxy(request("/internal/staging-tools"));
      expect(response.status).toBe(404);
    });

    it("401s with WWW-Authenticate when no credentials are sent", () => {
      process.env.INTERNAL_TOOLS_USER = "staff";
      process.env.INTERNAL_TOOLS_PASSWORD = "s3cret";

      const response = proxy(request("/internal/staging-tools"));
      expect(response.status).toBe(401);
      expect(response.headers.get("WWW-Authenticate")).toContain("Basic");
    });

    it("401s on wrong credentials", () => {
      process.env.INTERNAL_TOOLS_USER = "staff";
      process.env.INTERNAL_TOOLS_PASSWORD = "s3cret";

      const wrong = `Basic ${btoa("staff:wrong")}`;
      const response = proxy(request("/internal/staging-tools", wrong));
      expect(response.status).toBe(401);
    });

    it("passes through on correct credentials", () => {
      process.env.INTERNAL_TOOLS_USER = "staff";
      process.env.INTERNAL_TOOLS_PASSWORD = "s3cret";

      const correct = `Basic ${btoa("staff:s3cret")}`;
      const response = proxy(request("/internal/staging-tools", correct));
      expect(response.status).toBe(200);
      expect(response.headers.get("x-middleware-next")).toBe("1");
    });

    it("does not gate other paths", () => {
      delete process.env.INTERNAL_TOOLS_USER;
      delete process.env.INTERNAL_TOOLS_PASSWORD;

      const response = proxy(request("/"));
      expect(response.status).toBe(200);
    });
  });
});
