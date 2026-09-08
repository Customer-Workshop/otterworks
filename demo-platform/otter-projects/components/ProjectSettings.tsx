"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import { apiSend } from "@/lib/client";
import { DISPATCHERS, type DispatcherKind, type Project } from "@/lib/types";

const HELP: Record<DispatcherKind, string> = {
  webhook: "POST a signed JSON payload (prompt first) to the webhook URL — e.g. a Devin Automation webhook trigger. Falls back to DEVIN_WEBHOOK_URL when empty.",
  "devin-api": "Create the session directly via the Devin v3 API using DEVIN_API_KEY / DEVIN_ORG_ID.",
  none: "Do not dispatch automatically; tickets can still receive inbound Devin updates.",
};

export default function ProjectSettings({ project, onClose, onSaved }: { project: Project; onClose: () => void; onSaved: (p: Project) => void }) {
  const [form, setForm] = useState({
    name: project.name,
    description: project.description,
    repo: project.repo,
    promptTemplate: project.promptTemplate,
    dispatcher: project.dispatcher,
    webhookUrl: project.webhookUrl,
    createAsUserId: project.createAsUserId,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await apiSend<{ project: Project }>(`/api/projects/${project.key}`, "PATCH", form);
      onSaved(res.project);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`${project.key} settings`} onClose={onClose} wide>
      <form onSubmit={save} className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          Name
          <input className="input mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label className="text-sm">
          Repository
          <input className="input mt-1" value={form.repo} onChange={(e) => setForm({ ...form, repo: e.target.value })} placeholder="org/repo" />
        </label>
        <label className="text-sm sm:col-span-2">
          Description
          <textarea className="input mt-1" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </label>
        <label className="text-sm sm:col-span-2">
          Prompt template <span className="text-slate-500">— placeholders: {"{key} {title} {description} {repo} {type} {priority} {labels} {branch}"}; rendered as one line</span>
          <textarea className="input mt-1 font-mono text-xs" rows={3} value={form.promptTemplate} onChange={(e) => setForm({ ...form, promptTemplate: e.target.value })} />
        </label>
        <label className="text-sm">
          Devin dispatcher
          <select className="input mt-1" value={form.dispatcher} onChange={(e) => setForm({ ...form, dispatcher: e.target.value as DispatcherKind })}>
            {DISPATCHERS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <span className="mt-1 block text-xs text-slate-500">{HELP[form.dispatcher]}</span>
        </label>
        {form.dispatcher === "webhook" && (
          <label className="text-sm">
            Webhook URL
            <input className="input mt-1" value={form.webhookUrl} onChange={(e) => setForm({ ...form, webhookUrl: e.target.value })} placeholder="https://api.devin.ai/…/webhook" />
          </label>
        )}
        {form.dispatcher === "devin-api" && (
          <label className="text-sm">
            Create sessions as user id (optional)
            <input className="input mt-1" value={form.createAsUserId} onChange={(e) => setForm({ ...form, createAsUserId: e.target.value })} placeholder="google-oauth2|…" />
          </label>
        )}
        {error && (
          <p role="alert" className="text-sm text-red-600 sm:col-span-2">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
