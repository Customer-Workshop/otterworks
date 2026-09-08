"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import Header from "@/components/Header";
import { DevinBadge, LabelChip, PriorityBadge, TypeBadge } from "@/components/Badges";
import TicketDrawer from "@/components/TicketDrawer";
import ProjectSettings from "@/components/ProjectSettings";
import NewTicketForm from "@/components/NewTicketForm";
import { apiGet, apiSend } from "@/lib/client";
import { STATUSES, type Project, type Status, type Ticket } from "@/lib/types";

const POLL_MS = 5000;

function Card({ ticket, onOpen, dragging = false }: { ticket: Ticket; onOpen?: (key: string) => void; dragging?: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: ticket.key });
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      data-ticket={ticket.key}
      onClick={() => onOpen?.(ticket.key)}
      className={`cursor-grab rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-sm hover:border-slate-400 ${
        isDragging && !dragging ? "opacity-30" : ""
      } ${dragging ? "rotate-1 shadow-lg" : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-slate-500">{ticket.key}</span>
        <div className="flex items-center gap-1">
          <TypeBadge type={ticket.type} />
          <PriorityBadge priority={ticket.priority} />
        </div>
      </div>
      <p className="mt-1 font-medium leading-snug">{ticket.title}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {ticket.devin.sessionId || ticket.devin.dispatchedAt ? <DevinBadge status={ticket.devin.status} /> : null}
        {ticket.labels.map((l) => (
          <LabelChip key={l} label={l} />
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
        <span>{ticket.assignee ? `@${ticket.assignee}` : "unassigned"}</span>
        {ticket.prUrl && (
          <a href={ticket.prUrl} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline" onClick={(e) => e.stopPropagation()}>
            PR ↗
          </a>
        )}
      </div>
    </div>
  );
}

function Column({ status, tickets, onOpen }: { status: Status; tickets: Ticket[]; onOpen: (key: string) => void }) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  return (
    <section
      ref={setNodeRef}
      data-column={status}
      className={`flex min-h-[60vh] w-64 shrink-0 flex-col rounded-xl border p-2 ${isOver ? "border-violet-400 bg-violet-50" : "border-slate-200 bg-slate-50"}`}
    >
      <header className="flex items-center justify-between px-1 pb-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{status}</h2>
        <span className="rounded-full bg-slate-200 px-2 text-xs text-slate-700">{tickets.length}</span>
      </header>
      <div className="flex flex-1 flex-col gap-2">
        {tickets.map((t) => (
          <Card key={t.key} ticket={t} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}

export default function Board({ projectKey, initialTicket }: { projectKey: string; initialTicket: string | null }) {
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<Ticket | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(initialTicket);
  const [showSettings, setShowSettings] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [filter, setFilter] = useState("");

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor));

  const load = useCallback(async () => {
    try {
      const [p, t] = await Promise.all([
        apiGet<{ project: Project }>(`/api/projects/${projectKey}`),
        apiGet<{ tickets: Ticket[] }>(`/api/projects/${projectKey}/tickets`),
      ]);
      setProject(p.project);
      setTickets(t.tickets);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
      if (tickets === null) setTickets([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectKey]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  function open(key: string | null) {
    setOpenKey(key);
    const qs = key ? `?ticket=${encodeURIComponent(key)}` : "";
    router.replace(`/projects/${projectKey}${qs}`, { scroll: false });
  }

  const byStatus = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const map: Record<Status, Ticket[]> = { Backlog: [], Ready: [], "In Progress": [], "In Review": [], Done: [] };
    for (const t of tickets ?? []) {
      if (q && !`${t.key} ${t.title} ${t.labels.join(" ")} ${t.assignee}`.toLowerCase().includes(q)) continue;
      map[t.status].push(t);
    }
    for (const s of STATUSES) map[s].sort((a, b) => b.updatedAt - a.updatedAt);
    return map;
  }, [tickets, filter]);

  function onDragStart(e: DragStartEvent) {
    setActive(tickets?.find((t) => t.key === e.active.id) ?? null);
  }

  async function onDragEnd(e: DragEndEvent) {
    setActive(null);
    const key = String(e.active.id);
    const status = e.over?.id as Status | undefined;
    const t = tickets?.find((x) => x.key === key);
    if (!t || !status || !(STATUSES as readonly string[]).includes(status) || t.status === status) return;
    setTickets((prev) => prev?.map((x) => (x.key === key ? { ...x, status } : x)) ?? prev);
    try {
      await apiSend(`/api/tickets/${key}/transition`, "POST", { status });
    } catch (err) {
      setError(err instanceof Error ? err.message : "transition failed");
    } finally {
      await load();
    }
  }

  return (
    <div className="min-h-screen">
      <Header crumbs={[{ label: projectKey }]} />
      <main className="px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{project?.name ?? projectKey}</h1>
            <p className="text-xs text-slate-500">
              {project?.repo || "no repo"} · dispatcher: <span className="font-medium">{project?.dispatcher ?? "…"}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              aria-label="Filter tickets"
              className="input w-56"
              placeholder="Filter…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button type="button" className="btn-secondary" onClick={() => setShowSettings(true)}>
              Settings
            </button>
            <button type="button" className="btn-primary" onClick={() => setShowNew(true)}>
              New ticket
            </button>
          </div>
        </div>
        {error && (
          <div role="alert" className="mt-3 flex items-center justify-between rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
            <button type="button" className="btn-xs" onClick={() => setError(null)}>
              Dismiss
            </button>
          </div>
        )}
        {tickets === null ? (
          <p className="mt-6 text-sm text-slate-500">Loading board…</p>
        ) : (
          <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
            <div className="mt-4 flex gap-3 overflow-x-auto pb-4">
              {STATUSES.map((s) => (
                <Column key={s} status={s} tickets={byStatus[s]} onOpen={open} />
              ))}
            </div>
            <DragOverlay>{active ? <Card ticket={active} dragging /> : null}</DragOverlay>
          </DndContext>
        )}
      </main>
      {openKey && project && (
        <TicketDrawer
          ticketKey={openKey}
          project={project}
          onClose={() => open(null)}
          onChanged={() => void load()}
        />
      )}
      {showSettings && project && (
        <ProjectSettings
          project={project}
          onClose={() => setShowSettings(false)}
          onSaved={(p) => {
            setProject(p);
            setShowSettings(false);
          }}
        />
      )}
      {showNew && (
        <NewTicketForm
          projectKey={projectKey}
          onClose={() => setShowNew(false)}
          onCreated={(t) => {
            setShowNew(false);
            void load();
            open(t.key);
          }}
        />
      )}
    </div>
  );
}
