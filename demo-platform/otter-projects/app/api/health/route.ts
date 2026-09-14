import { NextResponse } from "next/server";

// Unauthenticated liveness/readiness target. Never touches DynamoDB so a
// control-plane blip cannot flap the pod.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET(): NextResponse {
  return NextResponse.json({ ok: true, service: "otter-projects" });
}
