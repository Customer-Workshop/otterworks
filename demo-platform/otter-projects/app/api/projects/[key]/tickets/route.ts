import { NextRequest, NextResponse } from "next/server";
import { errorResponse, readJson, requireAuth } from "@/lib/auth";
import { TicketService } from "@/lib/service";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Params = { params: Promise<{ key: string }> };

export async function GET(req: NextRequest, { params }: Params): Promise<NextResponse> {
  try {
    requireAuth(req);
    const { key } = await params;
    const svc = new TicketService();
    await svc.getProject(key.toUpperCase());
    return NextResponse.json({ tickets: await svc.listTickets(key.toUpperCase()) });
  } catch (err) {
    return errorResponse(err);
  }
}

export async function POST(req: NextRequest, { params }: Params): Promise<NextResponse> {
  try {
    const actor = requireAuth(req);
    const { key } = await params;
    const body = await readJson<Record<string, unknown>>(req);
    const ticket = await new TicketService().createTicket(key.toUpperCase(), body, actor.name);
    return NextResponse.json({ ticket }, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
