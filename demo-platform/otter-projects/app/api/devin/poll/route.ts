import { NextRequest, NextResponse } from "next/server";
import { errorResponse, hasValidApiKey } from "@/lib/auth";
import { UnauthorizedError } from "@/lib/session";
import { pollDevinSessions } from "@/lib/poller";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 55;

/** Hit by the Kubernetes CronJob every 60s. API-key only. */
export async function POST(req: NextRequest): Promise<NextResponse> {
  try {
    if (!hasValidApiKey(req)) throw new UnauthorizedError();
    return NextResponse.json(await pollDevinSessions());
  } catch (err) {
    return errorResponse(err);
  }
}
