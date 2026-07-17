import { listTenants } from "@/lib/control";
import { env } from "@/lib/env";
import { liveStateByNamespace, liveStateForNamespace } from "@/lib/k8s";
import type { Tenant } from "@/lib/types";

// Reconcile the control-table status against live pods: a tenant whose only
// unhealthy pods are the planted-bug services (see env.expectedDegradedServices)
// is `active`; a non-terminal tenant with an UNEXPECTED crashlooping pod is
// surfaced as `error`. Without the exclusion every OtterWorks tenant would read
// `error` forever, because admin-service crash-loops by design on the golden app.
function reconcileStatus(t: Tenant): Tenant {
  if (!t.live) return t;
  const { totalPods } = t.live;
  if (t.status === "draining" || t.status === "free") return t;
  const expected = env.expectedDegradedServices;
  const unexpectedlyDown = t.live.services.filter(
    (s) => !s.ready && !expected.has(s.name),
  );
  if (totalPods > 0 && unexpectedlyDown.length === 0) return { ...t, status: "active" };
  if (t.status === "deploying") return t;
  const crashing = unexpectedlyDown.some((s) => s.restarts >= 3);
  if (crashing) return { ...t, status: "error" };
  return t;
}

/** control-table items joined with live cluster state (GET /api/tenants). */
export async function getTenantsWithLiveState(): Promise<Tenant[]> {
  const [tenants, live] = await Promise.all([
    listTenants(),
    liveStateByNamespace().catch(() => new Map()),
  ]);
  return tenants.map((t) => reconcileStatus({ ...t, live: live.get(t.namespace) ?? undefined }));
}

export async function getTenantWithLiveState(t: Tenant): Promise<Tenant> {
  const live = await liveStateForNamespace(t.namespace).catch(() => null);
  return reconcileStatus({ ...t, live: live ?? undefined });
}
