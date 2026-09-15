import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const email = new URL(request.url).searchParams.get("email")?.trim() ?? "";
  if (!email) {
    return NextResponse.json({ detail: "Enter an email address." }, { status: 400 });
  }

  const upstream = new URL("/alerts", getApiBaseUrl());
  upstream.searchParams.set("email", email);

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
      { detail: "Couldn't load your watchlist right now." },
      { status: 502 }
    );
  }
}
