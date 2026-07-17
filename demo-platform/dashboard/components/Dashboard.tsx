"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiSend } from "@/lib/client";
import TenantsTable from "@/components/TenantsTable";
import CheckoutDialog from "@/components/CheckoutDialog";
import ReaperPanel from "@/components/ReaperPanel";
import AuditView from "@/components/AuditView";
import type { Tenant } from "@/lib/types";

type Tab = "tenants" | "reaper" | "audit";

export default function Dashboard() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("tenants");
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCheckout, setShowCheckout] = useState(false);

  const loadTenants = useCallback(async () => {
    setError(null);
    try {
      setTenants(await apiGet<Tenant[]>("/api/tenants"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTenants();
    const t = setInterval(() => void loadTenants(), 5000);
    return () => clearInterval(t);
  }, [loadTenants]);

  async function logout() {
    await apiSend("/api/auth/logout", "POST").catch(() => undefined);
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">OtterWorks Demo Ops</h1>
          <p className="text-sm text-slate-500">Ephemeral demo tenant control plane</p>
        </div>
        <div className="flex items-center gap-2">
          {tab === "tenants" && (
            <button className="btn-primary" onClick={() => setShowCheckout(true)}>
              Checkout
            </button>
          )}
          <button className="btn-secondary" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <nav className="mt-6 flex gap-1 border-b border-slate-200">
        <TabButton active={tab === "tenants"} onClick={() => setTab("tenants")}>
          Tenants
        </TabButton>
        <TabButton active={tab === "reaper"} onClick={() => setTab("reaper")}>
          Reaper
        </TabButton>
        <TabButton active={tab === "audit"} onClick={() => setTab("audit")}>
          Audit
        </TabButton>
      </nav>

      <main className="mt-6">
        {error && (
          <p className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        )}
        {tab === "tenants" &&
          (loading ? (
            <p className="text-sm text-slate-500">Loading tenants…</p>
          ) : (
            <TenantsTable tenants={tenants} onChanged={loadTenants} />
          ))}
        {tab === "reaper" && <ReaperPanel />}
        {tab === "audit" && <AuditView />}
      </main>

      <CheckoutDialog
        open={showCheckout}
        onClose={() => setShowCheckout(false)}
        onDone={loadTenants}
      />
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
        active
          ? "border-slate-900 text-slate-900"
          : "border-transparent text-slate-500 hover:text-slate-700"
      }`}
    >
      {children}
    </button>
  );
}
