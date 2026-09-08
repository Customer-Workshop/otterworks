"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import { apiSend } from "@/lib/client";
import { PRIORITIES, TICKET_TYPES, type Priority, type Ticket, type TicketType } from "@/lib/types";

export default function NewTicketForm({
  projectKey,
  onClose,
  onCreated,
}: {
  projectKey: string;
  onClose: () => void;
  onCreated: (t: Ticket) => void;
}) {
  const [form, setForm] = useState({ title: "", description: "", type: "story" as TicketType, priority: "Medium" as Priority, labels: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await apiSend<{ ticket: Ticket }>(`/api/projects/${projectKey}/tickets`, "POST", {
        ...form,
        labels: form.labels.split(",").map((s) => s.trim()).filter(Boolean),
      });
      onCreated(res.ticket);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to create ticket");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="New ticket" onClose={onClose} wide>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm sm:col-span-2">
          Title
          <input className="input mt-1" required autoFocus value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </label>
        <label className="text-sm sm:col-span-2">
          Description (markdown)
          <textarea className="input mt-1 font-mono text-xs" rows={8} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </label>
        <label className="text-sm">
          Type
          <select className="input mt-1" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as TicketType })}>
            {TICKET_TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Priority
          <select className="input mt-1" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value as Priority })}>
            {PRIORITIES.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="text-sm sm:col-span-2">
          Labels (comma-separated)
          <input className="input mt-1" value={form.labels} onChange={(e) => setForm({ ...form, labels: e.target.value })} placeholder="api-gateway, devin" />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600 sm:col-span-2">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy || !form.title.trim()}>
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
