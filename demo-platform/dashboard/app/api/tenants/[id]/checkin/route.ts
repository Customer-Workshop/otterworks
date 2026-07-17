import { withSession, json, error } from "@/lib/api";
import { appendAudit, checkin, getTenant } from "@/lib/control";
import { createRunnerJob, RunnerNotConfiguredError } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = withSession(async (_req, { actor, params }) => {
  const id = params?.id;
  if (!id) return error(400, "missing id");

  const tenant = await getTenant(id);
  if (!tenant) return error(404, "not found");

  await checkin(id);
  await appendAudit({ tenantId: id, action: "checkin", actor });

  try {
    await createRunnerJob({ action: "teardown", tenantId: id });
  } catch (err) {
    if (err instanceof RunnerNotConfiguredError) {
      return json({ ok: true, warning: "teardown job not enqueued (runner not configured)" }, 202);
    }
    const detail = err instanceof Error ? err.message : "teardown job create failed";
    await appendAudit({ tenantId: id, action: "checkin", actor, detail: `teardown failed: ${detail}` });
    return json({ ok: true, warning: `teardown job failed to enqueue: ${detail}` }, 202);
  }

  return json({ ok: true, status: "draining" });
});
