import { NextRequest, NextResponse } from "next/server";
import { errorResponse, requireAuth } from "@/lib/auth";
import { TicketService } from "@/lib/service";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Params = { params: Promise<{ key: string }> };

/** "Assign to Devin" button: sets assignee=devin and dispatches via the project's dispatcher. */
export async function POST(req: NextRequest, { params }: Params): Promise<NextResponse> {
  try {
    const actor = requireAuth(req);
    const { key } = await params;
    const result = await new TicketService().assignToDevin(key, actor.name);
    return NextResponse.json(result, { status: result.ok ? 200 : 502 });
  } catch (err) {
    return errorResponse(err);
  }
}
