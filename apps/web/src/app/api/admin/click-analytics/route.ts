import { getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type RequestBody = {
  adminToken?: string;
};

export async function POST(request: Request) {
  const upstreamUrl = new URL(
    "/admin/affiliate/click-analytics",
    getApiBaseUrl()
  );

  try {
    const payload = (await request.json()) as RequestBody;
    if (!payload.adminToken?.trim()) {
      return NextResponse.json(
        { detail: "Admin token is required" },
        { status: 401 }
      );
    }

    const upstreamResponse = await fetch(upstreamUrl, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "X-Admin-Token": payload.adminToken.trim(),
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
      { detail: "Click analytics API is unavailable" },
      { status: 502 }
    );
  }
}
