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
    const body = await readJson<{ add?: unknown; remove?: unknown; labels?: unknown }>(req);
    return NextResponse.json({ ticket: await new TicketService().addLabels(key, body.add ?? body.labels, body.remove, actor.name) });
  } catch (err) {
    return errorResponse(err);
  }
}
