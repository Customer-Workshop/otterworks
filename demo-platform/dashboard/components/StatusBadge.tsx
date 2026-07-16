import type { TenantStatus } from "@/lib/types";

const STYLES: Record<TenantStatus, string> = {
  free: "bg-slate-100 text-slate-600",
  reserved: "bg-amber-100 text-amber-800",
  deploying: "bg-blue-100 text-blue-800",
  active: "bg-green-100 text-green-800",
  draining: "bg-orange-100 text-orange-800",
  error: "bg-red-100 text-red-800",
};

export default function StatusBadge({ status }: { status: TenantStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}
