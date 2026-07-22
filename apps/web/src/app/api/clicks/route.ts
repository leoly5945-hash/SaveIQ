import { getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const upstreamUrl = new URL("/clicks", getApiBaseUrl());

  try {
    const upstreamResponse = await fetch(upstreamUrl, {
      body: await request.text(),
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "content-type":
          request.headers.get("content-type") ?? "application/json",
        "user-agent": request.headers.get("user-agent") ?? "dealhunter-web",
      },
      method: "POST",
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
      { detail: "Click tracking API is unavailable" },
      { status: 502 }
    );
  }
}
