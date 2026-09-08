import { NextRequest, NextResponse } from "next/server";
import { errorResponse, HttpError, requireWebhookAuth } from "@/lib/auth";
import { TicketService } from "@/lib/service";
import type { InboundDevinEvent } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Inbound Devin → ticket stream. Auth: `Authorization: Bearer <PROJECTS_API_KEY>`
 * or `X-OtterProjects-Signature: sha256=<hmac(body, PROJECTS_WEBHOOK_SECRET)>`.
 * The ticket key comes from `?ticket=` or the body's `ticket` field.
 */
export async function POST(req: NextRequest): Promise<NextResponse> {
  try {
    const raw = await req.text();
    requireWebhookAuth(req, raw);
    let body: Partial<InboundDevinEvent> & { message_id?: unknown };
    try {
      body = raw ? (JSON.parse(raw) as typeof body) : {};
    } catch {
      throw new HttpError(400, "invalid JSON body");
    }
    const ticket = (req.nextUrl.searchParams.get("ticket") || (typeof body.ticket === "string" ? body.ticket : "")).trim().toUpperCase();
    if (!ticket) throw new HttpError(400, "ticket is required (query ?ticket= or body.ticket)");
    const updated = await new TicketService().applyDevinEvent({
      ticket,
      session_id: typeof body.session_id === "string" ? body.session_id : undefined,
      session_url: typeof body.session_url === "string" ? body.session_url : undefined,
      status: typeof body.status === "string" ? body.status : undefined,
      message: typeof body.message === "string" ? body.message : undefined,
      pr_url: typeof body.pr_url === "string" ? body.pr_url : undefined,
      message_id: typeof body.message_id === "string" ? body.message_id : undefined,
    });
    return NextResponse.json({ ok: true, ticket: updated });
  } catch (err) {
    return errorResponse(err);
  }
}
