import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const upstream = new URL("/acquire", getApiBaseUrl());
  upstream.search = incoming.search;

  try {
    const res = await fetch(upstream, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "The acquisition advisor is unavailable right now." },
      { status: 502 }
    );
  }
}
