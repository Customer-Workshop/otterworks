import { NextResponse } from "next/server";

// Probe target at /health (mirrors /api/health).
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET(): NextResponse {
  return NextResponse.json({ ok: true, service: "otter-projects" });
}
