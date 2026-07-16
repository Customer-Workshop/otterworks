import { listTenants } from "@/lib/control";
import { liveStateByNamespace, liveStateForNamespace } from "@/lib/k8s";
import type { Tenant } from "@/lib/types";

// Reconcile the control-table status against live pods: a tenant marked
// deploying whose pods are all Ready is really `active`; a non-terminal tenant
// with crashlooping pods is surfaced as `error`.
function reconcileStatus(t: Tenant): Tenant {
  if (!t.live) return t;
  const { readyPods, totalPods } = t.live;
  if (t.status === "draining" || t.status === "free") return t;
  if (totalPods > 0 && readyPods === totalPods) return { ...t, status: "active" };
  if (t.status === "deploying") return t;
  const crashing = t.live.services.some((s) => !s.ready && s.restarts >= 3);
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
