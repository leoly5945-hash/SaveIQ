import { getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    offerId: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { offerId } = await context.params;
  const upstreamUrl = new URL(`/search/offers/${offerId}`, getApiBaseUrl());

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
      { detail: "Offer detail API is unavailable" },
      { status: 502 }
    );
  }
}
