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
    return NextResponse.json({ project: await new TicketService().getProject(key.toUpperCase()) });
  } catch (err) {
    return errorResponse(err);
  }
}

export async function PATCH(req: NextRequest, { params }: Params): Promise<NextResponse> {
  try {
    requireAuth(req);
    const { key } = await params;
    const body = await readJson<Record<string, unknown>>(req);
    return NextResponse.json({ project: await new TicketService().updateProject(key.toUpperCase(), body) });
  } catch (err) {
    return errorResponse(err);
  }
}

export async function DELETE(req: NextRequest, { params }: Params): Promise<NextResponse> {
  try {
    requireAuth(req);
    const { key } = await params;
    await new TicketService().deleteProject(key.toUpperCase());
    return new NextResponse(null, { status: 204 });
  } catch (err) {
    return errorResponse(err);
  }
}
