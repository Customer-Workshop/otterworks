import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "@/components/layout/app-shell";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { billingApi, errorDetail, isEstateUnavailable, type Me, type Usage } from "./api";
import { EstateUnavailable } from "./estate-unavailable";

function monthRange(): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const iso = (value: Date) => value.toISOString().slice(0, 10);
  return { start: iso(start), end: iso(end) };
}

export default function BillingOverviewPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const range = monthRange();
    Promise.all([billingApi.me(), billingApi.usage(range.start, range.end)])
      .then(([account, currentUsage]) => {
        setMe(account);
        setUsage(currentUsage);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-6">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-otter-600">Billing</p>
          <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
        </div>
        {loading && <LoadingSpinner className="mx-auto my-16" size="lg" />}
        {!loading && isEstateUnavailable(error) && <EstateUnavailable detail={errorDetail(error)} />}
        {!loading && Boolean(error) && !isEstateUnavailable(error) && (
          <p role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">
            Billing details could not be loaded.
          </p>
        )}
        {!loading && me && usage && (
          <>
            <section className="grid gap-4 md:grid-cols-3">
              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p className="text-sm text-gray-500">Account</p>
                <h2 className="mt-1 text-xl font-semibold text-gray-900">{me.name}</h2>
                <p className="mt-2 text-sm text-gray-600">Status: {me.status}</p>
                <p className="text-sm text-gray-600">Tenant: {me.tenant_id}</p>
              </div>
              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p className="text-sm text-gray-500">Current plan</p>
                <h2 className="mt-1 text-xl font-semibold text-gray-900">
                  {me.entitlement[0]?.plan_code ?? "No plan"}
                </h2>
                <p className="mt-2 text-sm text-gray-600">
                  {me.entitlement[0]?.tier ?? "—"} · {me.entitlement[0]?.included_units ?? "—"} included units
                </p>
                <p className="text-sm text-gray-600">
                  ${me.entitlement[0]?.monthly_fee ?? "—"} / month
                </p>
                <Link to="/billing/plans" className="mt-3 inline-block text-sm font-medium text-otter-700 hover:underline">
                  View plans
                </Link>
              </div>
              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p className="text-sm text-gray-500">Customer balance</p>
                {me.customer ? (
                  <>
                    <h2 className="mt-1 text-xl font-semibold text-gray-900">{me.customer.cust_no}</h2>
                    <p className="mt-2 text-sm text-gray-600">Current: ${me.customer.cur_bal_amt}</p>
                    <p className="text-sm text-gray-600">Past due: ${me.customer.past_due_amt}</p>
                    <span className={`mt-3 inline-block rounded-full px-2 py-1 text-xs font-semibold ${me.customer.credit_hold_yn === "Y" ? "bg-red-100 text-red-800" : "bg-green-100 text-green-800"}`}>
                      {me.customer.credit_hold_yn === "Y" ? "Credit hold" : "Credit clear"}
                    </span>
                  </>
                ) : (
                  <p className="mt-2 text-sm text-gray-600">No legacy customer record</p>
                )}
              </div>
            </section>
            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900">Usage this month</h2>
                <Link to="/billing/invoices" className="text-sm font-medium text-otter-700 hover:underline">View invoices</Link>
              </div>
              <div className="mt-4 grid gap-6 lg:grid-cols-2">
                <div>
                  <h3 className="text-sm font-medium text-gray-700">Summary</h3>
                  <dl className="mt-2 divide-y divide-gray-100">
                    {usage.summary.map((row, index) => (
                      <div key={index} className="flex justify-between gap-4 py-2 text-sm">
                        {Object.entries(row).map(([key, value]) => (
                          <span key={key} className={key === Object.keys(row)[0] ? "text-gray-600" : "font-medium text-gray-900"}>{String(value ?? "—")}</span>
                        ))}
                      </div>
                    ))}
                  </dl>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-gray-700">Recent events</h3>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="text-xs uppercase text-gray-500"><tr><th className="py-2">Occurred</th><th className="py-2">Kind</th><th className="py-2 text-right">Units</th></tr></thead>
                      <tbody className="divide-y divide-gray-100">
                        {usage.events.map((event) => (
                          <tr key={event.id}><td className="py-2">{event.occurred_at}</td><td className="py-2">{event.kind}</td><td className="py-2 text-right">{event.units}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
              <p className="mt-5 text-xs text-gray-500">Source: OW_BILLING legacy estate (Oracle)</p>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
