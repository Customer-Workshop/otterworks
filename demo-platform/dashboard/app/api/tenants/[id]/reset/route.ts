import { withSession, json, error } from "@/lib/api";
import { appendAudit, getTenant } from "@/lib/control";
import { createRunnerJob, RunnerNotConfiguredError } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = withSession(async (_req, { actor, params }) => {
  const id = params?.id;
  if (!id) return error(400, "missing id");

  const tenant = await getTenant(id);
  if (!tenant) return error(404, "not found");

  let jobName: string;
  try {
    jobName = await createRunnerJob({ action: "inject", tenantId: id, scenario: "reset" });
  } catch (err) {
    if (err instanceof RunnerNotConfiguredError) {
      return json({ ok: false, warning: "reset job not enqueued (runner not configured)" }, 202);
    }
    const detail = err instanceof Error ? err.message : "job create failed";
    await appendAudit({ tenantId: id, action: "reset", actor, detail: `failed: ${detail}` });
    return error(502, "reset job failed to enqueue");
  }

  await appendAudit({ tenantId: id, action: "reset", actor });
  return json({ ok: true, job: jobName });
});
