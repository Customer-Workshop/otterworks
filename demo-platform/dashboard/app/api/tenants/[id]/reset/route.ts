import { withSession, json, error } from "@/lib/api";
import { appendAudit, getTenant } from "@/lib/control";
import { createRunnerJob } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = withSession(async (_req, { actor, params }) => {
  const id = params?.id;
  if (!id) return error(400, "missing id");

  const tenant = await getTenant(id);
  if (!tenant) return error(404, "not found");

  await appendAudit({ tenantId: id, action: "reset", actor });
  const jobName = await createRunnerJob({ action: "inject", tenantId: id, scenario: "reset" });
  return json({ ok: true, job: jobName });
});
