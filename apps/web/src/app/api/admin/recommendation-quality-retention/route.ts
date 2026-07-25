import { getApiBaseUrl } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type RequestBody = {
  adminToken?: string;
  confirm?: string;
  dryRun?: boolean;
  keepLatestTraces?: number;
};

export async function POST(request: Request) {
  const upstreamUrl = new URL(
    "/admin/affiliate/recommendation-quality/retention",
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

    const body = JSON.stringify({
      confirm: payload.confirm,
      dry_run: payload.dryRun ?? true,
      keep_latest_traces: payload.keepLatestTraces ?? 50,
    });
    const upstreamResponse = await fetch(upstreamUrl, {
      body,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Admin-Token": payload.adminToken.trim(),
      },
      method: "POST",
    });
    const responseBody = await upstreamResponse.text();
    return new NextResponse(responseBody, {
      status: upstreamResponse.status,
      headers: {
        "content-type":
          upstreamResponse.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Recommendation retention API is unavailable" },
      { status: 502 }
    );
  }
}
