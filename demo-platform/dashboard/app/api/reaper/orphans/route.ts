import { withSession, json } from "@/lib/api";
import { listTenants } from "@/lib/control";
import { listTenantNamespaces } from "@/lib/k8s";
import type { Orphan } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Live tenant namespaces with no matching TENANT# record are orphans — a
// preview of what the sweeper would GC.
export const GET = withSession(async () => {
  const [tenants, namespaces] = await Promise.all([
    listTenants(),
    listTenantNamespaces().catch(() => [] as string[]),
  ]);
  const known = new Set(tenants.map((t) => t.namespace));
  const orphans: Orphan[] = namespaces
    .filter((ns) => !known.has(ns))
    .map((ns) => ({ kind: "namespace", name: ns, detail: "no matching TENANT# record" }));
  return json(orphans);
});
