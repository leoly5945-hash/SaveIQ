import { getBrandName } from "@/lib/config";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({
    status: "ok",
    service: `${getBrandName()} Web`,
    version: "0.1.0",
  });
}
