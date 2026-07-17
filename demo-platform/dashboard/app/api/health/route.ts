import { NextResponse } from "next/server";

// Unauthenticated liveness/readiness probe target (see helm dashboard
// Deployment). Deliberately does NOT touch DynamoDB or AWS — it only reports
// that the process is up, so a transient control-plane blip never flaps the pod.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET(): NextResponse {
  return NextResponse.json({ ok: true });
}
