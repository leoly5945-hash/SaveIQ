import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const upstream = new URL("/alerts", getApiBaseUrl());
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request." }, { status: 400 });
  }

  try {
    const res = await fetch(upstream, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "content-type":
          res.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Couldn't set the alert right now." },
      { status: 502 }
    );
  }
}
