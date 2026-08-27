import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

/** Constant-time-ish string compare so auth isn't trivially timeable. */
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) {
    return false;
  }
  let mismatch = 0;
  for (let i = 0; i < a.length; i += 1) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

/**
 * Gates the internal QA/staging dashboard behind HTTP Basic Auth.
 *
 * Fails closed: if INTERNAL_TOOLS_USER/INTERNAL_TOOLS_PASSWORD aren't set on
 * this service, /internal/* 404s for everyone (including staff) rather than
 * being left open. Set both (sync: false) in the Render dashboard to enable
 * access - they are not committed anywhere.
 */
function guardInternalTools(request: NextRequest): NextResponse | null {
  if (!request.nextUrl.pathname.startsWith("/internal")) {
    return null;
  }

  const user = process.env.INTERNAL_TOOLS_USER;
  const pass = process.env.INTERNAL_TOOLS_PASSWORD;
  if (!user || !pass) {
    return new NextResponse(null, { status: 404 });
  }

  const authHeader = request.headers.get("authorization") ?? "";
  const expected = `Basic ${btoa(`${user}:${pass}`)}`;
  if (authHeader && safeEqual(authHeader, expected)) {
    return null;
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Internal tools"' },
  });
}

export function proxy(request: NextRequest) {
  const blocked = guardInternalTools(request);
  if (blocked) {
    return blocked;
  }

  const response = NextResponse.next();

  if (
    process.env.STAGING_NOINDEX === "true" ||
    process.env.PRODUCTION_NOINDEX === "true"
  ) {
    response.headers.set("X-Robots-Tag", "noindex, nofollow");
  }

  return response;
}
