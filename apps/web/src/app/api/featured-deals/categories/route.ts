import { getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const upstreamResponse = await fetch(
      new URL("/featured-deals/categories", getApiBaseUrl()),
      { cache: "no-store", headers: { Accept: "application/json" } }
    );
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
      { detail: "Featured deals API is unavailable" },
      { status: 502 }
    );
  }
}
