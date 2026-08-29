import { getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ offerId: string }>;
};

// Headers the backend needs to log a real (non-bot) click and attribute it.
const FORWARD_HEADERS = [
  "user-agent",
  "referer",
  "x-forwarded-for",
  "sec-purpose",
  "x-purpose",
  "purpose",
];

const REDIRECT_HEADERS = {
  "Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
  "X-Robots-Tag": "noindex, nofollow",
};

/**
 * First-party outbound click hop. The browser hits `saveiq.ca/go/<offer>`,
 * this handler asks the API to log the click server-side (so the log never
 * depends on a beacon surviving navigation) and 302s the visitor on to the
 * affiliate URL, which now carries our SubID for reconciliation.
 */
export async function GET(request: Request, context: RouteContext) {
  const { offerId } = await context.params;
  const requestUrl = new URL(request.url);

  // Behind Render/Cloudflare the request URL is http://localhost:<port>; the
  // real public origin is in the forwarded headers.
  const forwardedHost =
    request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const forwardedProto = request.headers.get("x-forwarded-proto") ?? "https";
  const publicOrigin = forwardedHost
    ? `${forwardedProto}://${forwardedHost}`
    : requestUrl.origin;
  const home = new URL("/", publicOrigin);

  const upstream = new URL(`/go/${encodeURIComponent(offerId)}`, getApiBaseUrl());
  const target = requestUrl.searchParams.get("t");
  if (target) {
    upstream.searchParams.set("t", target);
  }
  const anonymousId = requestUrl.searchParams.get("aid");
  if (anonymousId) {
    upstream.searchParams.set("aid", anonymousId);
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  for (const name of FORWARD_HEADERS) {
    const value = request.headers.get(name);
    if (value) {
      headers[name] = value;
    }
  }

  try {
    const upstreamResponse = await fetch(upstream, {
      cache: "no-store",
      headers,
      method: "GET",
      redirect: "manual",
    });
    const location = upstreamResponse.headers.get("location");
    if (
      location &&
      [301, 302, 303, 307, 308].includes(upstreamResponse.status)
    ) {
      return NextResponse.redirect(location, {
        headers: REDIRECT_HEADERS,
        status: 302,
      });
    }
  } catch {
    // fall through to the safe redirect below
  }

  // Unknown offer or API unavailable: don't leave the visitor at a dead end.
  return NextResponse.redirect(home, { status: 302 });
}
