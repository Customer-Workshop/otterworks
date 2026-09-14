"use client";

import { useCallback, useEffect, useState } from "react";
import { DevinBadge, LabelChip, PriorityBadge, TypeBadge } from "@/components/Badges";
import Markdown from "@/components/Markdown";
import { apiGet, apiSend, timeAgo } from "@/lib/client";
import { PRIORITIES, STATUSES, TICKET_TYPES, type Project, type Ticket, type TicketDetail } from "@/lib/types";

const POLL_MS = 4000;

export default function TicketDrawer({
  ticketKey,
  project,
  onClose,
  onChanged,
}: {
  ticketKey: string;
  project: Project;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ title: "", description: "", branch: "", prUrl: "" });
  const [labelInput, setLabelInput] = useState("");
  const [assigneeInput, setAssigneeInput] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [tab, setTab] = useState<"comments" | "activity">("comments");

  const load = useCallback(async () => {
    try {
      const d = await apiGet<TicketDetail>(`/api/tickets/${ticketKey}`);
      setDetail(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load ticket");
    }
  }, [ticketKey]);

  useEffect(() => {
    setDetail(null);
    setEditing(false);
    void load();
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !editing) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, editing]);

  async function run(label: string, fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(label);
    setError(null);
    try {
      await fn();
      await load();
      onChanged();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : `${label} failed`);
      return false;
    } finally {
      setBusy(null);
    }
  }

  const t: Ticket | undefined = detail?.ticket;

  function patch(body: Record<string, unknown>) {
    return run("update", () => apiSend(`/api/tickets/${ticketKey}`, "PATCH", body));
  }

  function startEdit() {
    if (!t) return;
    setDraft({ title: t.title, description: t.description, branch: t.branch, prUrl: t.prUrl });
    setEditing(true);
  }

  const hasDevin = Boolean(t?.devin.sessionId || t?.devin.dispatchedAt);

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-slate-900/30" onClick={onClose} role="presentation">
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Ticket ${ticketKey}`}
        className="flex h-full w-full max-w-2xl flex-col overflow-y-auto bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-mono text-slate-500">{ticketKey}</span>
            {t && <TypeBadge type={t.type} />}
            {t && <PriorityBadge priority={t.priority} />}
            {hasDevin && <DevinBadge status={t?.devin.status} />}
          </div>
          <div className="flex items-center gap-2">
            {t && !editing && (
              <button type="button" className="btn-xs" onClick={startEdit}>
                Edit
              </button>
            )}
            <button type="button" className="btn-xs" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        {error && (
          <div role="alert" className="mx-5 mt-3 flex items-center justify-between rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
            <button type="button" className="btn-xs" onClick={() => setError(null)}>
              Dismiss
            </button>
          </div>
        )}

        {!t ? (
          <p className="px-5 py-6 text-sm text-slate-500">{error ? "" : "Loading…"}</p>
        ) : (
          <div className="grid gap-5 px-5 py-4 md:grid-cols-[1fr_220px]">
            <div className="min-w-0">
              {editing ? (
                <form
                  className="grid gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void patch(draft).then((ok) => ok && setEditing(false));
                  }}
                >
                  <label className="text-sm">
                    Title
                    <input className="input mt-1" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} required />
                  </label>
                  <label className="text-sm">
                    Description (markdown)
                    <textarea className="input mt-1 font-mono text-xs" rows={12} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
                  </label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="text-sm">
                      Branch
                      <input className="input mt-1" value={draft.branch} onChange={(e) => setDraft({ ...draft, branch: e.target.value })} />
                    </label>
                    <label className="text-sm">
                      PR URL
                      <input className="input mt-1" value={draft.prUrl} onChange={(e) => setDraft({ ...draft, prUrl: e.target.value })} />
                    </label>
                  </div>
                  <div className="flex justify-end gap-2">
                    <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>
                      Cancel
                    </button>
                    <button type="submit" className="btn-primary" disabled={busy !== null}>
                      Save
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <h2 className="text-lg font-semibold leading-snug">{t.title}</h2>
                  <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                    {t.description ? <Markdown>{t.description}</Markdown> : <p className="text-sm text-slate-400">No description.</p>}
                  </div>
                </>
              )}

              <section className="mt-5 rounded-lg border border-violet-200 bg-violet-50 p-3" data-testid="devin-panel">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-violet-900">Devin</h3>
                  <button
                    type="button"
                    className="rounded-md bg-violet-600 px-3 py-1 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-50"
                    disabled={busy !== null || project.dispatcher === "none"}
                    title={project.dispatcher === "none" ? "Project dispatcher is 'none' — change it in Settings" : `Dispatch via ${project.dispatcher}`}
                    onClick={() =>
                      run("assign to Devin", async () => {
                        const res = await fetch(`/api/tickets/${ticketKey}/devin`, { method: "POST" });
                        const data = (await res.json()) as { ok?: boolean; error?: string };
                        if (!res.ok || !data.ok) throw new Error(data.error || `dispatch failed (${res.status})`);
                      })
                    }
                  >
                    {busy === "assign to Devin" ? "Dispatching…" : hasDevin ? "Re-dispatch to Devin" : "Assign to Devin"}
                  </button>
                </div>
                {hasDevin ? (
                  <dl className="mt-2 grid grid-cols-[90px_1fr] gap-x-2 gap-y-1 text-xs">
                    <dt className="text-violet-700">Status</dt>
                    <dd className="font-medium">{t.devin.status ?? "—"}</dd>
                    <dt className="text-violet-700">Session</dt>
                    <dd className="truncate">
                      {t.devin.sessionUrl ? (
                        <a href={t.devin.sessionUrl} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline">
                          {t.devin.sessionId ?? t.devin.sessionUrl}
                        </a>
                      ) : (
                        t.devin.sessionId ?? `dispatched via ${t.devin.dispatcher ?? "?"}, awaiting session`
                      )}
                    </dd>
                    <dt className="text-violet-700">PR</dt>
                    <dd className="truncate">
                      {t.prUrl ? (
                        <a href={t.prUrl} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline">
                          {t.prUrl}
                        </a>
                      ) : (
                        "—"
                      )}
                    </dd>
                    <dt className="text-violet-700">Latest</dt>
                    <dd className="whitespace-pre-wrap break-words">
                      {t.devin.lastMessage ?? "—"}
                      {t.devin.lastMessageAt && <span className="ml-1 text-violet-600">({timeAgo(t.devin.lastMessageAt)})</span>}
                    </dd>
                  </dl>
                ) : (
                  <p className="mt-2 text-xs text-violet-800">
                    No session yet. Add the <code>devin</code> label, assign to <code>devin</code>, or click Assign to Devin.
                  </p>
                )}
              </section>

              <div className="mt-5 flex gap-4 border-b border-slate-200 text-sm">
                {(["comments", "activity"] as const).map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setTab(k)}
                    className={`-mb-px border-b-2 px-1 pb-2 capitalize ${tab === k ? "border-slate-900 font-medium" : "border-transparent text-slate-500"}`}
                  >
                    {k} ({k === "comments" ? detail?.comments.length : detail?.events.length})
                  </button>
                ))}
              </div>

              {tab === "comments" ? (
                <div className="mt-3">
                  <ul className="space-y-3">
                    {detail?.comments.length === 0 && <li className="text-sm text-slate-400">No comments yet.</li>}
                    {detail?.comments.map((c) => (
                      <li key={c.id} className={`rounded-lg border p-3 ${c.source === "devin" ? "border-violet-200 bg-violet-50" : "border-slate-200"}`} data-source={c.source}>
                        <div className="flex items-center gap-2 text-xs text-slate-500">
                          <span className={`font-medium ${c.source === "devin" ? "text-violet-800" : "text-slate-800"}`}>
                            {c.source === "devin" ? "◆ " : ""}
                            {c.author}
                          </span>
                          <span>{timeAgo(c.createdAt)}</span>
                        </div>
                        <Markdown className="mt-1">{c.body}</Markdown>
                      </li>
                    ))}
                  </ul>
                  <form
                    className="mt-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (!comment.trim()) return;
                      void run("comment", () => apiSend(`/api/tickets/${ticketKey}/comments`, "POST", { body: comment })).then((ok) => ok && setComment(""));
                    }}
                  >
                    <label htmlFor="comment" className="sr-only">
                      Add a comment
                    </label>
                    <textarea id="comment" className="input" rows={3} placeholder="Add a comment (markdown)…" value={comment} onChange={(e) => setComment(e.target.value)} />
                    <div className="mt-2 flex justify-end">
                      <button type="submit" className="btn-primary" disabled={busy !== null || !comment.trim()}>
                        Comment
                      </button>
                    </div>
                  </form>
                </div>
              ) : (
                <ol className="mt-3 space-y-2 text-sm">
                  {detail?.events.length === 0 && <li className="text-slate-400">No activity.</li>}
                  {[...(detail?.events ?? [])].reverse().map((e) => (
                    <li key={e.id} className="flex gap-2">
                      <span className="w-14 shrink-0 text-xs text-slate-400">{timeAgo(e.createdAt)}</span>
                      <span>
                        <span className="font-medium">{e.actor}</span> {e.action}
                        {e.detail && <span className="text-slate-600"> — {e.detail}</span>}
                      </span>
                    </li>
                  ))}
                  {detail?.deliveries.map((d) => (
                    <li key={d.id} className="flex gap-2">
                      <span className="w-14 shrink-0 text-xs text-slate-400">{timeAgo(d.createdAt)}</span>
                      <span className={d.status === "ok" ? "text-emerald-700" : "text-red-700"}>
                        {d.dispatcher} delivery {d.status} ({d.attempts} attempt{d.attempts === 1 ? "" : "s"}
                        {d.responseStatus ? `, HTTP ${d.responseStatus}` : ""}){d.error ? ` — ${d.error}` : ""}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <div className="space-y-4 text-sm">
              <Field label="Status">
                <select className="input" value={t.status} onChange={(e) => run("transition", () => apiSend(`/api/tickets/${ticketKey}/transition`, "POST", { status: e.target.value }))} aria-label="Status">
                  {STATUSES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </Field>
              <Field label="Type">
                <select className="input" value={t.type} onChange={(e) => patch({ type: e.target.value })} aria-label="Type">
                  {TICKET_TYPES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </Field>
              <Field label="Priority">
                <select className="input" value={t.priority} onChange={(e) => patch({ priority: e.target.value })} aria-label="Priority">
                  {PRIORITIES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </Field>
              <Field label="Assignee">
                <form
                  className="flex gap-1"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void run("assign", () => apiSend(`/api/tickets/${ticketKey}/assign`, "POST", { assignee: assigneeInput })).then((ok) => ok && setAssigneeInput(""));
                  }}
                >
                  <input className="input" list="assignees" placeholder={t.assignee || "unassigned"} value={assigneeInput} onChange={(e) => setAssigneeInput(e.target.value)} aria-label="Assignee" />
                  <datalist id="assignees">
                    <option value="devin" />
                  </datalist>
                  <button type="submit" className="btn-xs" disabled={busy !== null}>
                    Set
                  </button>
                </form>
                <p className="mt-1 text-xs text-slate-500">Current: {t.assignee ? `@${t.assignee}` : "unassigned"}</p>
              </Field>
              <Field label="Labels">
                <div className="flex flex-wrap gap-1">
                  {t.labels.map((l) => (
                    <button
                      key={l}
                      type="button"
                      title="Remove label"
                      onClick={() => run("labels", () => apiSend(`/api/tickets/${ticketKey}/labels`, "POST", { remove: [l] }))}
                    >
                      <LabelChip label={l} />
                    </button>
                  ))}
                </div>
                <form
                  className="mt-1 flex gap-1"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!labelInput.trim()) return;
                    void run("labels", () => apiSend(`/api/tickets/${ticketKey}/labels`, "POST", { add: labelInput.split(",") })).then((ok) => ok && setLabelInput(""));
                  }}
                >
                  <input className="input" placeholder="add label" value={labelInput} onChange={(e) => setLabelInput(e.target.value)} aria-label="Add label" />
                  <button type="submit" className="btn-xs" disabled={busy !== null}>
                    Add
                  </button>
                </form>
              </Field>
              <Field label="Repo">
                <span className="break-all text-xs">{t.repo || "—"}</span>
              </Field>
              <Field label="Branch">
                <span className="break-all text-xs">{t.branch || "—"}</span>
              </Field>
              <Field label="Updated">
                <span className="text-xs">{timeAgo(t.updatedAt)}</span>
              </Field>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      {children}
    </div>
  );
}
