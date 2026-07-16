import { NextRequest } from "next/server";
import { withSession, json } from "@/lib/api";
import { scanAudit } from "@/lib/control";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = withSession(async (req: NextRequest) => {
  const raw = Number(req.nextUrl.searchParams.get("limit"));
  const limit = Number.isFinite(raw) && raw > 0 ? Math.min(raw, 500) : 100;
  const events = await scanAudit(limit);
  return json(events);
});
