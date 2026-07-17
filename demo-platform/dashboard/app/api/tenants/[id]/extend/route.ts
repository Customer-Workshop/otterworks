import { NextRequest } from "next/server";
import { withSession, json, error } from "@/lib/api";
import { appendAudit, extend, getTenant } from "@/lib/control";
import { ttlToSeconds } from "@/lib/util";
import type { ExtendRequest } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = withSession(async (req: NextRequest, { actor, params }) => {
  const id = params?.id;
  if (!id) return error(400, "missing id");

  const body = (await req.json().catch(() => ({}))) as ExtendRequest;
  const ttlStr = typeof body.ttl === "string" ? body.ttl : "";
  const ttlSeconds = ttlToSeconds(ttlStr);
  if (ttlSeconds === null) return error(400, "invalid ttl");

  const tenant = await getTenant(id);
  if (!tenant) return error(404, "not found");

  const expiresAt = await extend(id, ttlSeconds, tenant.expiresAt);
  await appendAudit({ tenantId: id, action: "extend", actor, detail: `ttl=${ttlStr}` });

  return json({ ok: true, expiresAt });
});
