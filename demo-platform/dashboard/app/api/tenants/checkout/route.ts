import { NextRequest } from "next/server";
import { withSession, json, error } from "@/lib/api";
import { appendAudit, checkout } from "@/lib/control";
import { createRunnerJob, RunnerNotConfiguredError } from "@/lib/jobs";
import { env } from "@/lib/env";
import { isValidId, randomIdSuffix, sanitizeId, ttlToSeconds } from "@/lib/util";
import type { CheckoutRequest, TenantTier } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = withSession(async (req: NextRequest, { actor }) => {
  const body = (await req.json().catch(() => ({}))) as CheckoutRequest;

  const rawId = typeof body.id === "string" && body.id.trim() ? body.id : `a${randomIdSuffix()}`;
  const id = sanitizeId(rawId);
  if (!isValidId(id)) return error(400, "invalid tenant id");

  const owner = typeof body.owner === "string" && body.owner.trim() ? body.owner.trim() : actor;
  const branch =
    typeof body.branch === "string" && body.branch.trim() ? body.branch.trim() : `workshop-${id}`;
  const tier: TenantTier = body.tier === "B" ? "B" : "A";
  const imageTag = typeof body.image_tag === "string" && body.image_tag ? body.image_tag : undefined;

  const ttlStr = typeof body.ttl === "string" && body.ttl ? body.ttl : "8h";
  const ttlSeconds = ttlToSeconds(ttlStr);
  if (ttlSeconds === null) return error(400, "invalid ttl");

  const tenant = await checkout({
    id,
    owner,
    branch,
    tier,
    imageTag,
    ttlSeconds,
    hostSuffix: env.hostSuffix,
  });

  await appendAudit({
    tenantId: id,
    action: "checkout",
    actor,
    detail: `branch=${branch} tier=${tier} ttl=${ttlStr}`,
  });

  // Fire the deploy runner Job. If the runner image isn't configured yet the
  // tenant record still exists (status=deploying) and the error surfaces.
  try {
    await createRunnerJob({
      action: "deploy",
      tenantId: id,
      branch,
      tier,
      imageTag,
      ttl: ttlStr,
      hostSuffix: env.hostSuffix,
    });
  } catch (err) {
    if (err instanceof RunnerNotConfiguredError) {
      return json({ tenant, warning: "deploy job not enqueued (runner not configured)" }, 202);
    }
    const detail = err instanceof Error ? err.message : "job create failed";
    await appendAudit({ tenantId: id, action: "deploy_fail", actor, detail });
    return json({ tenant, warning: `deploy job failed to enqueue: ${detail}` }, 202);
  }

  return json(tenant, 201);
});
