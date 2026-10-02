import { getAmazonTag, getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ asin: string }>;
};

const ASIN_RE = /^[A-Za-z0-9]{10}$/;
const SOURCE_RE = /^[a-z]{1,20}$/;

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
 * First-party hop for the Amazon button on price-check pages. Those pages are
 * not offers, so their buy button used to link straight to Amazon and the click
 * was never logged. The API logs it (with the page it came from) and answers
 * with the tagged Amazon URL.
 *
 * A shopper must never lose their way to Amazon because our log is down: if the
 * API fails, or answers with anything that isn't an Amazon.ca URL, we redirect
 * to the tagged product page ourselves.
 */
export async function GET(request: Request, context: RouteContext) {
  const { asin: rawAsin } = await context.params;
  const requestUrl = new URL(request.url);

  if (!ASIN_RE.test(rawAsin)) {
    const forwardedHost =
      request.headers.get("x-forwarded-host") ?? request.headers.get("host");
    const forwardedProto = request.headers.get("x-forwarded-proto") ?? "https";
    const origin = forwardedHost ? `${forwardedProto}://${forwardedHost}` : requestUrl.origin;
    return NextResponse.redirect(new URL("/", origin), { status: 302 });
  }
  const asin = rawAsin.toUpperCase();
  const requested = requestUrl.searchParams.get("src") ?? "check";
  const source = SOURCE_RE.test(requested) ? requested : "other";

  const fallback = new URL(`https://www.amazon.ca/dp/${asin}`);
  fallback.searchParams.set("tag", getAmazonTag());
  fallback.searchParams.set("ascsubtag", source);

  const upstream = new URL(`/go/amazon/${asin}`, getApiBaseUrl());
  upstream.searchParams.set("src", source);

  const headers: Record<string, string> = { Accept: "application/json" };
  for (const name of FORWARD_HEADERS) {
    const value = request.headers.get(name);
    if (value) {
      headers[name] = value;
    }
  }
  // Cloudflare rejects a client-sent `CF-Connecting-IP`, so pass the visitor's
  // IP under our own name (same as the offer hop).
  const clientIp = request.headers.get("cf-connecting-ip");
  if (clientIp) {
    headers["x-saveiq-client-ip"] = clientIp;
  }

  let destination = fallback.toString();
  try {
    const upstreamResponse = await fetch(upstream, {
      cache: "no-store",
      headers,
      method: "GET",
      redirect: "manual",
    });
    const location = upstreamResponse.headers.get("location");
    if (location && [301, 302, 303, 307, 308].includes(upstreamResponse.status)) {
      const target = new URL(location);
      if (target.protocol === "https:" && target.hostname === "www.amazon.ca") {
        destination = target.toString();
      }
    }
  } catch {
    // keep the fallback
  }

  return NextResponse.redirect(destination, { headers: REDIRECT_HEADERS, status: 302 });
}
