import { NextRequest, NextResponse } from "next/server";
import { errorResponse, readJson, requireAuth } from "@/lib/auth";
import { TicketService } from "@/lib/service";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Params = { params: Promise<{ key: string }> };

export async function POST(req: NextRequest, { params }: Params): Promise<NextResponse> {
  try {
    const actor = requireAuth(req);
    const { key } = await params;
    const body = await readJson<{ assignee?: unknown }>(req);
    const svc = new TicketService();
    const ticket = body.assignee === "devin" ? (await svc.assignToDevin(key, actor.name)).ticket : await svc.assign(key, body.assignee, actor.name);
    return NextResponse.json({ ticket });
  } catch (err) {
    return errorResponse(err);
  }
}
