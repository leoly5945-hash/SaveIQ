import { getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL("/search", getApiBaseUrl());
  upstreamUrl.search = incomingUrl.search;

  try {
    const upstreamResponse = await fetch(upstreamUrl, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });
    const body = await upstreamResponse.text();
    return new NextResponse(body, {
      status: upstreamResponse.status,
      headers: {
        "content-type":
          upstreamResponse.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Search API is unavailable" },
      { status: 502 }
    );
  }
}
