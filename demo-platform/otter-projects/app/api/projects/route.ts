import { NextRequest, NextResponse } from "next/server";
import { errorResponse, readJson, requireAuth } from "@/lib/auth";
import { TicketService } from "@/lib/service";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";


export async function GET(req: NextRequest): Promise<NextResponse> {
  try {
    requireAuth(req);
    return NextResponse.json({ projects: await new TicketService().listProjects() });
  } catch (err) {
    return errorResponse(err);
  }
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  try {
    requireAuth(req);
    const body = await readJson<Record<string, unknown>>(req);
    const project = await new TicketService().createProject(body);
    return NextResponse.json({ project }, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
