import { withSession, json } from "@/lib/api";
import { getTenantsWithLiveState } from "@/lib/tenants";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = withSession(async () => {
  const tenants = await getTenantsWithLiveState();
  return json(tenants);
});
