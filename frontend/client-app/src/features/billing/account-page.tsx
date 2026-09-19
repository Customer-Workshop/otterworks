import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { billingApi, errorDetail, isEstateUnavailable, type Customer } from "./api";
import { EstateUnavailable } from "./estate-unavailable";

export default function BillingAccountPage() {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    billingApi.customer().then(setCustomer).catch(setError).finally(() => setLoading(false));
  }, []);

  const fields = customer ? Object.entries(customer).filter(([key]) => key !== "attributes") : [];

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-6">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-otter-600">Billing</p>
          <h1 className="text-2xl font-bold text-gray-900">Account</h1>
        </div>
        {loading && <LoadingSpinner className="mx-auto my-16" size="lg" />}
        {!loading && isEstateUnavailable(error) && <EstateUnavailable detail={errorDetail(error)} />}
        {!loading && Boolean(error) && !isEstateUnavailable(error) && (
          <p role="alert" className="rounded-lg bg-gray-50 p-5 text-gray-700">No legacy customer record for this account</p>
        )}
        {!loading && customer && (
          <>
            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900">Key fields</h2>
              <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {fields.slice(0, 18).map(([key, value]) => (
                  <div key={key}><dt className="text-xs uppercase text-gray-500">{key}</dt><dd className="mt-1 text-sm text-gray-900">{String(value ?? "—")}</dd></div>
                ))}
              </dl>
            </section>
            <details className="rounded-xl border border-gray-200 bg-white shadow-sm">
              <summary className="cursor-pointer px-5 py-4 font-semibold text-gray-900">All {fields.length} legacy fields</summary>
              <div className="overflow-x-auto border-t border-gray-100">
                <table className="w-full text-left text-sm">
                  <tbody className="divide-y divide-gray-100">
                    {fields.map(([key, value]) => <tr key={key}><th className="w-1/3 px-5 py-2 font-medium text-gray-600">{key}</th><td className="px-5 py-2 text-gray-900">{String(value ?? "—")}</td></tr>)}
                  </tbody>
                </table>
              </div>
            </details>
            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900">Attributes (EAV)</h2>
              <table className="mt-4 w-full text-left text-sm">
                <thead className="text-xs uppercase text-gray-500"><tr><th className="py-2">Name</th><th className="py-2">Value</th><th className="py-2">Type</th></tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {(customer.attributes ?? []).map((attribute, index) => <tr key={index}><td className="py-2">{String(attribute.attr_name ?? "—")}</td><td className="py-2">{String(attribute.attr_value ?? "—")}</td><td className="py-2">{String(attribute.attr_type ?? "—")}</td></tr>)}
                </tbody>
              </table>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
