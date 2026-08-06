import { getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const upstreamUrl = new URL("/user/feedback", getApiBaseUrl());
  const userId = request.headers.get("x-anonymous-user-id");

  try {
    if (!userId?.trim()) {
      return NextResponse.json(
        { detail: "X-Anonymous-User-Id header is required" },
        { status: 401 }
      );
    }
    const payload = await request.text();
    const upstreamResponse = await fetch(upstreamUrl, {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Anonymous-User-Id": userId.trim(),
      },
      body: payload,
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
      { detail: "User feedback API is unavailable" },
      { status: 502 }
    );
  }
}
