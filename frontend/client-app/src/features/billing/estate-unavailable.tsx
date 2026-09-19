export function EstateUnavailable({ detail }: Readonly<{ detail?: string }>) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <p className="font-semibold">
        Billing is temporarily unavailable — the legacy billing system isn&apos;t reachable
      </p>
      {detail && <p className="mt-1 text-amber-800">{detail}</p>}
    </div>
  );
}
