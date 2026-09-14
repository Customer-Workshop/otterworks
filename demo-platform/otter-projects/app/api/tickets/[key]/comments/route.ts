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
    const body = await readJson<{ body?: unknown; author?: unknown }>(req);
    const author = actor.via === "session" ? actor.name : typeof body.author === "string" && body.author.trim() ? body.author.trim().slice(0, 120) : actor.name;
    const comment = await new TicketService().addComment(key, body.body, author);
    return NextResponse.json({ comment }, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
