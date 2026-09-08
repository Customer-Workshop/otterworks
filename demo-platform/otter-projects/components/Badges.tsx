import type { Priority, TicketType } from "@/lib/types";

const PRIORITY: Record<Priority, string> = {
  Low: "bg-slate-100 text-slate-600",
  Medium: "bg-blue-100 text-blue-800",
  High: "bg-orange-100 text-orange-800",
  Critical: "bg-red-100 text-red-800",
};

const TYPE: Record<TicketType, string> = {
  story: "bg-emerald-100 text-emerald-800",
  bug: "bg-rose-100 text-rose-800",
  task: "bg-sky-100 text-sky-800",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <span className={`chip ${PRIORITY[priority]}`}>{priority}</span>;
}

export function TypeBadge({ type }: { type: TicketType }) {
  return <span className={`chip ${TYPE[type]}`}>{type}</span>;
}

export function LabelChip({ label }: { label: string }) {
  const devin = label === "devin";
  return <span className={`chip ${devin ? "bg-violet-100 text-violet-800" : "bg-slate-100 text-slate-700"}`}>{label}</span>;
}

export function DevinBadge({ status }: { status?: string }) {
  return (
    <span className="chip gap-1 bg-violet-600 text-white" title="Devin session attached">
      <span aria-hidden>◆</span> Devin{status ? ` · ${status}` : ""}
    </span>
  );
}
