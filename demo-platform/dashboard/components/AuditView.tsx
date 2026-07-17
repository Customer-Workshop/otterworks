"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/client";
import { formatTimestamp } from "@/lib/format";
import type { AuditEvent } from "@/lib/types";

export default function AuditView() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      setEvents(await apiGet<AuditEvent[]>("/api/audit?limit=100"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <h3 className="text-base font-semibold">Audit log</h3>
        <button className="btn-xs" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {error && <p className="px-4 py-3 text-sm text-red-600">{error}</p>}
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">Tenant</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">Actor</th>
            <th className="px-3 py-2 font-medium">Detail</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {events.map((e, i) => (
            <tr key={`${e.tenantId}-${e.ts}-${i}`} className="hover:bg-slate-50">
              <td className="px-3 py-2 font-mono text-xs">{formatTimestamp(e.ts)}</td>
              <td className="px-3 py-2 font-mono">{e.tenantId}</td>
              <td className="px-3 py-2">{e.action}</td>
              <td className="px-3 py-2">{e.actor}</td>
              <td className="px-3 py-2 text-slate-500">{e.detail ?? "—"}</td>
            </tr>
          ))}
          {events.length === 0 && !error && (
            <tr>
              <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                No audit events yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
