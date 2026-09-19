import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { billingApi, errorDetail, isEstateUnavailable, type Invoice } from "./api";
import { EstateUnavailable } from "./estate-unavailable";

type InvoiceLines = Array<Record<string, string | number | null>>;

export default function BillingInvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [lines, setLines] = useState<Record<string, InvoiceLines>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    billingApi.invoices().then(setInvoices).catch(setError).finally(() => setLoading(false));
  }, []);

  const toggle = (invoiceId: string) => {
    if (expanded === invoiceId) {
      setExpanded(null);
      return;
    }
    setExpanded(invoiceId);
    if (!lines[invoiceId]) {
      billingApi.invoiceLines(invoiceId)
        .then((value) => setLines((current) => ({ ...current, [invoiceId]: value })))
        .catch(setError);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-6">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-otter-600">Billing</p>
          <h1 className="text-2xl font-bold text-gray-900">Invoices</h1>
        </div>
        {loading && <LoadingSpinner className="mx-auto my-16" size="lg" />}
        {!loading && isEstateUnavailable(error) && <EstateUnavailable detail={errorDetail(error)} />}
        {!loading && Boolean(error) && !isEstateUnavailable(error) && <p role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">Invoices could not be loaded.</p>}
        {!loading && !error && (
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr><th className="px-5 py-3">Period</th><th className="px-5 py-3">Status</th><th className="px-5 py-3 text-right">Subtotal</th><th className="px-5 py-3 text-right">Tax</th><th className="px-5 py-3 text-right">Total</th></tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {invoices.map((invoice) => (
                  <tr key={invoice.invoice_id} className="cursor-pointer hover:bg-gray-50" onClick={() => toggle(invoice.invoice_id)}>
                    <td className="px-5 py-3">{invoice.period_start} — {invoice.period_end}</td>
                    <td className="px-5 py-3"><span className="rounded-full bg-gray-100 px-2 py-1 text-xs font-semibold">{invoice.status}</span></td>
                    <td className="px-5 py-3 text-right">${invoice.subtotal}</td>
                    <td className="px-5 py-3 text-right">${invoice.tax}</td>
                    <td className="px-5 py-3 text-right font-semibold">${invoice.total}</td>
                  </tr>
                ))}
                {expanded && lines[expanded] && (
                  <tr>
                    <td colSpan={5} className="bg-gray-50 px-5 py-4">
                      <h2 className="font-medium text-gray-700">Invoice lines</h2>
                      <div className="mt-2 space-y-2">
                        {lines[expanded].map((line, index) => (
                          <div key={index} className="flex flex-wrap gap-4 text-sm text-gray-600">
                            {Object.entries(line).map(([key, value]) => <span key={key}><strong>{key}:</strong> {String(value ?? "—")}</span>)}
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
