import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { billingApi, errorDetail, isEstateUnavailable, type Me, type Plan } from "./api";
import { BillingAlert } from "./alert";
import { EstateUnavailable } from "./estate-unavailable";

const today = () => new Date().toISOString().slice(0, 10);

export default function BillingPlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [effectiveOn, setEffectiveOn] = useState(today());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [refreshWarning, setRefreshWarning] = useState("");
  const [success, setSuccess] = useState("");

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([billingApi.listPlans(), billingApi.me()])
      .then(([availablePlans, account]) => {
        setPlans(availablePlans);
        setMe(account);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const currentPlan = me?.entitlement[0]?.plan_code;
  const submit = (planId: string) => {
    setSaving(true);
    setSuccess("");
    setSubmitError(null);
    setRefreshWarning("");
    billingApi.changePlan(planId, effectiveOn)
      .then(
        (result) => {
          setSuccess("Plan change saved.");
          setSelectedPlan(null);
          setMe((current) => current ? { ...current, entitlement: result.entitlement } : current);
          return billingApi.me();
        },
        (error) => {
          setSubmitError(error);
          return null;
        },
      )
      .then(
        (account) => {
          if (account) {
            setMe(account);
          }
        },
        () => {
          setRefreshWarning("Plan change saved, but the account could not be refreshed.");
        },
      )
      .finally(() => setSaving(false));
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-6">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-otter-600">Billing</p>
          <h1 className="text-2xl font-bold text-gray-900">Plans</h1>
        </div>
        {loading && <LoadingSpinner className="mx-auto my-16" size="lg" />}
        {!loading && isEstateUnavailable(error) && <EstateUnavailable detail={errorDetail(error)} />}
        {!loading && Boolean(error) && !isEstateUnavailable(error) && (
          <BillingAlert message="Plans could not be loaded." onDismiss={() => setError(null)} />
        )}
        {!loading && isEstateUnavailable(submitError) && <EstateUnavailable detail={errorDetail(submitError)} />}
        {!loading && Boolean(submitError) && !isEstateUnavailable(submitError) && (
          <BillingAlert
            message={errorDetail(submitError) ?? "Plan change was not accepted."}
            onDismiss={() => setSubmitError(null)}
          />
        )}
        {success && <BillingAlert message={success} tone="success" onDismiss={() => setSuccess("")} />}
        {refreshWarning && (
          <BillingAlert
            message={refreshWarning}
            tone="warning"
            onDismiss={() => setRefreshWarning("")}
          />
        )}
        {!loading && !error && (
          <div className="grid gap-4 md:grid-cols-3">
            {plans.map((plan) => {
              const current = plan.plan_code === currentPlan;
              return (
                <article key={plan.plan_id} className={`rounded-xl border bg-white p-5 shadow-sm ${current ? "border-otter-500 ring-2 ring-otter-100" : "border-gray-200"}`}>
                  {current && <span className="rounded-full bg-otter-100 px-2 py-1 text-xs font-semibold text-otter-800">Current plan</span>}
                  <h2 className="mt-3 text-xl font-semibold text-gray-900">{plan.plan_code}</h2>
                  <p className="mt-1 text-sm text-gray-600">{plan.tier}</p>
                  <p className="mt-4 text-2xl font-bold text-gray-900">${plan.monthly_fee}<span className="text-sm font-normal"> / month</span></p>
                  <p className="mt-2 text-sm text-gray-600">{plan.included_units} included units</p>
                  <button type="button" disabled={current} onClick={() => setSelectedPlan(plan.plan_id)} className="mt-5 rounded-lg bg-otter-600 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-gray-300">
                    {current ? "Current plan" : "Switch to this plan"}
                  </button>
                  {selectedPlan === plan.plan_id && (
                    <form className="mt-4 space-y-3 border-t border-gray-100 pt-4" onSubmit={(event) => { event.preventDefault(); submit(plan.plan_id); }}>
                      <label htmlFor={`effective-${plan.plan_id}`} className="block text-sm font-medium text-gray-700">Effective date</label>
                      <input id={`effective-${plan.plan_id}`} type="date" value={effectiveOn} onChange={(event) => setEffectiveOn(event.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                      <button type="submit" disabled={saving} className="rounded-lg border border-otter-600 px-3 py-2 text-sm font-semibold text-otter-700 disabled:opacity-50">
                        {saving ? "Saving…" : "Confirm change"}
                      </button>
                    </form>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
}
