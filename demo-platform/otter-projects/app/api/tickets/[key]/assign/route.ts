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
    if (body.assignee === "devin") {
      const current = await svc.getTicket(key);
      if (current.assignee === "devin") return NextResponse.json({ ticket: current, ok: true });
      const result = await svc.assignToDevin(key, actor.name);
      return NextResponse.json(result, { status: result.ok ? 200 : 502 });
    }
    const ticket = await svc.assign(key, body.assignee, actor.name);
    return NextResponse.json({ ticket });
  } catch (err) {
    return errorResponse(err);
  }
}
