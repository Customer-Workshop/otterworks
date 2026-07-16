import { NextRequest } from "next/server";
import { withSession, json, error } from "@/lib/api";
import { appendAudit, getTenant } from "@/lib/control";
import { createRunnerJob } from "@/lib/jobs";
import type { InjectRequest } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = withSession(async (req: NextRequest, { actor, params }) => {
  const id = params?.id;
  if (!id) return error(400, "missing id");

  const body = (await req.json().catch(() => ({}))) as InjectRequest;
  const scenario = typeof body.scenario === "string" && body.scenario.trim() ? body.scenario.trim() : "";
  if (!scenario) return error(400, "missing scenario");

  const tenant = await getTenant(id);
  if (!tenant) return error(404, "not found");

  let jobName: string;
  try {
    jobName = await createRunnerJob({ action: "inject", tenantId: id, scenario });
  } catch {
    return json({ ok: false, warning: "inject job not enqueued (runner not configured)" }, 202);
  }

  await appendAudit({ tenantId: id, action: "inject", actor, detail: `scenario=${scenario}` });
  return json({ ok: true, job: jobName });
});
