import crypto from "node:crypto";
import { HttpError } from "@/lib/errors";
import { env } from "@/lib/env";
import { dispatch, type DispatchOptions } from "@/lib/dispatch";
import { getStore } from "@/lib/store";
import type { Store } from "@/lib/store/types";
import { projectKeyOf } from "@/lib/store/types";
import {
  DEFAULT_PROMPT_TEMPLATE,
  DEVIN_ASSIGNEE,
  DEVIN_LABEL,
  DISPATCHERS,
  PRIORITIES,
  STATUSES,
  TICKET_TYPES,
  type ActivityEvent,
  type Comment,
  type InboundDevinEvent,
  type Project,
  type Status,
  type Ticket,
  type TicketDetail,
} from "@/lib/types";

const PROJECT_KEY_RE = /^[A-Z][A-Z0-9]{1,9}$/;

export function str(v: unknown, max = 20_000): string {
  return typeof v === "string" ? v.slice(0, max) : "";
}

function oneOf<T extends readonly string[]>(v: unknown, allowed: T, fallback: T[number]): T[number] {
  return typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T[number]) : fallback;
}

const PRIVATE_HOST_RE = /^(localhost|.*\.local|.*\.internal|0\.0\.0\.0|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+|\[?::1\]?|\[?fe80:.*|\[?fc.*|\[?fd.*)$/i;

/**
 * Validate a project webhook target. Only http(s); outside LOCAL_MODE the
 * host must be public (no loopback, RFC1918, link-local/metadata, or
 * internal DNS suffixes) so a signed-in user cannot aim the server at
 * cluster-internal services.
 */
export function validateWebhookUrl(raw: unknown): string {
  const value = str(raw, 2000).trim();
  if (!value) return "";
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new HttpError(400, "webhookUrl must be an absolute http(s) URL");
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") throw new HttpError(400, "webhookUrl must use http or https");
  if (!env.localMode && (url.protocol !== "https:" || PRIVATE_HOST_RE.test(url.hostname))) {
    throw new HttpError(400, "webhookUrl must be a public https URL");
  }
  return value;
}

export function normalizeLabels(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  const out = new Set<string>();
  for (const l of v) if (typeof l === "string" && l.trim()) out.add(l.trim().toLowerCase().slice(0, 40));
  return [...out].slice(0, 20);
}

export class TicketService {
  constructor(
    private readonly store: Store = getStore(),
    private readonly dispatchOpts: DispatchOptions = {},
  ) {}

  // ----- projects -----

  listProjects(): Promise<Project[]> {
    return this.store.listProjects();
  }

  async getProject(key: string): Promise<Project> {
    const p = await this.store.getProject(key);
    if (!p) throw new HttpError(404, `project ${key} not found`);
    return p;
  }

  async createProject(input: Record<string, unknown>): Promise<Project> {
    const key = str(input.key).trim().toUpperCase();
    if (!PROJECT_KEY_RE.test(key)) throw new HttpError(400, "key must be 2-10 chars, A-Z0-9, starting with a letter");
    const now = Date.now();
    const project: Project = {
      key,
      name: str(input.name, 120).trim() || key,
      description: str(input.description, 4000),
      repo: str(input.repo, 200).trim(),
      promptTemplate: str(input.promptTemplate, 4000).trim() || DEFAULT_PROMPT_TEMPLATE,
      dispatcher: oneOf(input.dispatcher, DISPATCHERS, "webhook"),
      webhookUrl: validateWebhookUrl(input.webhookUrl),
      createAsUserId: str(input.createAsUserId, 200).trim(),
      createdAt: now,
      updatedAt: now,
    };
    if (!(await this.store.createProject(project))) throw new HttpError(409, `project ${key} already exists`);
    return project;
  }

  async updateProject(key: string, input: Record<string, unknown>): Promise<Project> {
    const p = await this.getProject(key);
    if ("name" in input) p.name = str(input.name, 120).trim() || p.name;
    if ("description" in input) p.description = str(input.description, 4000);
    if ("repo" in input) p.repo = str(input.repo, 200).trim();
    if ("promptTemplate" in input) p.promptTemplate = str(input.promptTemplate, 4000).trim() || DEFAULT_PROMPT_TEMPLATE;
    if ("dispatcher" in input) p.dispatcher = oneOf(input.dispatcher, DISPATCHERS, p.dispatcher);
    if ("webhookUrl" in input) p.webhookUrl = validateWebhookUrl(input.webhookUrl);
    if ("createAsUserId" in input) p.createAsUserId = str(input.createAsUserId, 200).trim();
    p.updatedAt = Date.now();
    await this.store.putProject(p);
    return p;
  }

  async deleteProject(key: string): Promise<void> {
    await this.getProject(key);
    await this.store.deleteProject(key);
  }

  // ----- tickets -----

  listTickets(projectKey: string): Promise<Ticket[]> {
    return this.store.listTickets(projectKey);
  }

  async getTicket(key: string): Promise<Ticket> {
    const t = await this.store.getTicket(key.toUpperCase());
    if (!t) throw new HttpError(404, `ticket ${key} not found`);
    return t;
  }

  async getTicketDetail(key: string): Promise<TicketDetail> {
    const ticket = await this.getTicket(key);
    const [comments, events, deliveries] = await Promise.all([
      this.store.listComments(ticket.key),
      this.store.listEvents(ticket.key),
      this.store.listDeliveries(ticket.key),
    ]);
    return { ticket, comments, events, deliveries };
  }

  async createTicket(projectKey: string, input: Record<string, unknown>, actor: string): Promise<Ticket> {
    const project = await this.getProject(projectKey);
    const title = str(input.title, 300).trim();
    if (!title) throw new HttpError(400, "title is required");
    const n = await this.store.nextTicketNumber(project.key);
    const now = Date.now();
    const ticket: Ticket = {
      key: `${project.key}-${n}`,
      projectKey: project.key,
      number: n,
      title,
      description: str(input.description),
      type: oneOf(input.type, TICKET_TYPES, "story"),
      priority: oneOf(input.priority, PRIORITIES, "Medium"),
      status: oneOf(input.status, STATUSES, "Backlog"),
      labels: normalizeLabels(input.labels),
      assignee: str(input.assignee, 120).trim(),
      repo: str(input.repo, 200).trim() || project.repo,
      branch: str(input.branch, 200).trim(),
      prUrl: str(input.prUrl, 2000).trim(),
      devin: {},
      createdAt: now,
      updatedAt: now,
    };
    await this.store.putTicket(ticket);
    await this.event(ticket.key, actor, "created", `${ticket.type} · ${ticket.priority}`);
    await this.maybeDispatch(ticket, actor, []);
    return (await this.store.getTicket(ticket.key)) ?? ticket;
  }

  async updateTicket(key: string, input: Record<string, unknown>, actor: string): Promise<Ticket> {
    const t = await this.getTicket(key);
    const before = { ...t, labels: [...t.labels] };
    const changes: string[] = [];
    if ("title" in input) {
      const v = str(input.title, 300).trim();
      if (v && v !== t.title) (t.title = v), changes.push("title");
    }
    if ("description" in input && str(input.description) !== t.description) (t.description = str(input.description)), changes.push("description");
    if ("type" in input) {
      const v = oneOf(input.type, TICKET_TYPES, t.type);
      if (v !== t.type) (t.type = v), changes.push(`type → ${v}`);
    }
    if ("priority" in input) {
      const v = oneOf(input.priority, PRIORITIES, t.priority);
      if (v !== t.priority) (t.priority = v), changes.push(`priority → ${v}`);
    }
    if ("labels" in input) {
      const v = normalizeLabels(input.labels);
      if (v.join(",") !== t.labels.join(",")) (t.labels = v), changes.push(`labels → ${v.join(", ") || "none"}`);
    }
    if ("assignee" in input) {
      const v = str(input.assignee, 120).trim();
      if (v !== t.assignee) (t.assignee = v), changes.push(`assignee → ${v || "unassigned"}`);
    }
    if ("repo" in input) (t.repo = str(input.repo, 200).trim()), changes.push("repo");
    if ("branch" in input) (t.branch = str(input.branch, 200).trim()), changes.push("branch");
    if ("prUrl" in input) (t.prUrl = str(input.prUrl, 2000).trim()), changes.push("PR URL");
    if ("status" in input) {
      const v = oneOf(input.status, STATUSES, t.status);
      if (v !== t.status) (t.status = v), changes.push(`status ${before.status} → ${v}`);
    }
    if (changes.length === 0) return t;
    t.updatedAt = Date.now();
    await this.store.putTicket(t);
    await this.event(t.key, actor, "updated", changes.join("; "));
    await this.maybeDispatch(t, actor, before.labels, before.assignee);
    return (await this.store.getTicket(t.key)) ?? t;
  }

  async deleteTicket(key: string): Promise<void> {
    const t = await this.getTicket(key);
    await this.store.deleteTicket(t);
  }

  async transition(key: string, status: unknown, actor: string): Promise<Ticket> {
    const t = await this.getTicket(key);
    if (typeof status !== "string" || !(STATUSES as readonly string[]).includes(status)) {
      throw new HttpError(400, `status must be one of ${STATUSES.join(", ")}`);
    }
    if (t.status === status) return t;
    const from = t.status;
    t.status = status as Status;
    t.updatedAt = Date.now();
    await this.store.putTicket(t);
    await this.event(t.key, actor, "transitioned", `${from} → ${status}`);
    return t;
  }

  async addLabels(key: string, add: unknown, remove: unknown, actor: string): Promise<Ticket> {
    const t = await this.getTicket(key);
    const before = [...t.labels];
    const set = new Set(t.labels);
    for (const l of normalizeLabels(add)) set.add(l);
    for (const l of normalizeLabels(remove)) set.delete(l);
    t.labels = [...set].slice(0, 20);
    if (t.labels.join(",") === before.join(",")) return t;
    t.updatedAt = Date.now();
    await this.store.putTicket(t);
    await this.event(t.key, actor, "labels changed", t.labels.join(", ") || "none");
    await this.maybeDispatch(t, actor, before, t.assignee);
    return (await this.store.getTicket(t.key)) ?? t;
  }

  async assign(key: string, assignee: unknown, actor: string): Promise<Ticket> {
    const t = await this.getTicket(key);
    const v = str(assignee, 120).trim();
    if (v === t.assignee) return t;
    const before = t.assignee;
    t.assignee = v;
    t.updatedAt = Date.now();
    await this.store.putTicket(t);
    await this.event(t.key, actor, "assigned", v || "unassigned");
    await this.maybeDispatch(t, actor, t.labels, before);
    return (await this.store.getTicket(t.key)) ?? t;
  }

  async addComment(key: string, body: unknown, author: string, source: Comment["source"] = "human"): Promise<Comment> {
    const t = await this.getTicket(key);
    const text = str(body, 20_000).trim();
    if (!text) throw new HttpError(400, "body is required");
    const c: Comment = {
      id: crypto.randomUUID(),
      ticketKey: t.key,
      author,
      body: text,
      source,
      createdAt: Date.now(),
    };
    await this.store.addComment(c);
    await this.event(t.key, author, "commented");
    return c;
  }

  private async event(ticketKey: string, actor: string, action: string, detail?: string): Promise<ActivityEvent> {
    const e: ActivityEvent = { id: crypto.randomUUID(), ticketKey, actor, action, detail, createdAt: Date.now() };
    await this.store.addEvent(e);
    return e;
  }

  // ----- Devin: outbound -----

  /** Dispatch when the ticket *gains* the devin label / assignee and has no session yet. */
  private async maybeDispatch(t: Ticket, actor: string, prevLabels: string[], prevAssignee?: string): Promise<void> {
    const hadTrigger = prevLabels.includes(DEVIN_LABEL) || prevAssignee === DEVIN_ASSIGNEE;
    const hasTrigger = t.labels.includes(DEVIN_LABEL) || t.assignee === DEVIN_ASSIGNEE;
    if (!hasTrigger || hadTrigger) return;
    if (t.devin.sessionId || t.devin.dispatchedAt) return;
    if (!(await this.store.claimDispatch(t.key, Date.now()))) return;
    await this.dispatchToDevin(t.key, actor, true);
  }

  /** Explicit "Assign to Devin": sets the assignee (idempotent) and dispatches. */
  async assignToDevin(key: string, actor: string): Promise<{ ticket: Ticket; ok: boolean; error?: string }> {
    const t = await this.getTicket(key);
    if (t.assignee !== DEVIN_ASSIGNEE) {
      t.assignee = DEVIN_ASSIGNEE;
      t.updatedAt = Date.now();
      await this.store.putTicket(t);
      await this.event(t.key, actor, "assigned", DEVIN_ASSIGNEE);
    }
    return this.dispatchToDevin(key, actor);
  }

  /**
   * Explicit re-dispatch (POST /devin, Assign to Devin button) always sends;
   * automatic triggers pass `claimed=true` after winning `claimDispatch`.
   */
  async dispatchToDevin(key: string, actor: string, claimed = false): Promise<{ ticket: Ticket; ok: boolean; error?: string }> {
    const t = await this.getTicket(key);
    const project = await this.getProject(t.projectKey);
    if (!claimed && !t.devin.sessionId && !(await this.store.claimDispatch(t.key, Date.now()))) {
      const cur = (await this.store.getTicket(t.key)) ?? t;
      if (cur.devin.dispatchedAt && Date.now() - cur.devin.dispatchedAt < 30_000) {
        return { ticket: cur, ok: false, error: "a dispatch for this ticket is already in flight" };
      }
    }
    const result = await dispatch(project, t, this.dispatchOpts);
    await this.store.addDelivery(result.delivery);

    const fresh = (await this.store.getTicket(t.key)) ?? t;
    fresh.devin = { ...fresh.devin, dispatcher: project.dispatcher, dispatchedAt: Date.now() };
    if (result.ok) {
      if (result.session) {
        fresh.devin.sessionId = result.session.id;
        fresh.devin.sessionUrl = result.session.url;
        fresh.devin.status = result.session.status;
        await this.store.addComment({
          id: crypto.randomUUID(),
          ticketKey: fresh.key,
          author: DEVIN_ASSIGNEE,
          body: `Devin session started: ${result.session.url}`,
          source: "devin",
          createdAt: Date.now(),
        });
        await this.event(fresh.key, actor, "devin session started", result.session.url);
      } else {
        fresh.devin.status = fresh.devin.status ?? "dispatched";
        await this.event(fresh.key, actor, "dispatched to Devin", `webhook → ${result.delivery.target} (${result.delivery.attempts} attempt${result.delivery.attempts === 1 ? "" : "s"})`);
      }
      if (fresh.status === "Backlog" || fresh.status === "Ready") {
        const from = fresh.status;
        fresh.status = "In Progress";
        await this.event(fresh.key, "devin", "transitioned", `${from} → In Progress`);
      }
      fresh.updatedAt = Date.now();
      await this.store.putTicket(fresh);
      return { ticket: fresh, ok: true };
    }
    fresh.devin.dispatchedAt = undefined;
    fresh.updatedAt = Date.now();
    await this.store.putTicket(fresh);
    await this.event(fresh.key, actor, "devin dispatch failed", `${project.dispatcher}: ${result.delivery.error ?? "unknown error"}`);
    return { ticket: fresh, ok: false, error: result.delivery.error };
  }

  // ----- Devin: inbound -----

  /**
   * Apply an inbound Devin event (webhook or poller). Deduplicates messages by
   * `messageId` (falls back to a hash of message+timestamp).
   */
  async applyDevinEvent(
    ev: InboundDevinEvent & { message_id?: string; message_at?: number },
    actor = DEVIN_ASSIGNEE,
  ): Promise<Ticket> {
    const t = await this.getTicket(ev.ticket);
    const changes: string[] = [];
    const devin = { ...t.devin, seenMessageIds: [...(t.devin.seenMessageIds ?? [])] };

    if (ev.session_id && ev.session_id !== devin.sessionId) (devin.sessionId = ev.session_id), changes.push("session attached");
    if (ev.session_url && ev.session_url !== devin.sessionUrl) (devin.sessionUrl = ev.session_url), changes.push("session URL");
    if (ev.status && ev.status !== devin.status) (devin.status = ev.status), changes.push(`status ${ev.status}`);

    const message = str(ev.message, 20_000).trim();
    if (message) {
      const at = ev.message_at ?? Date.now();
      const id =
        ev.message_id ||
        crypto
          .createHash("sha1")
          .update(ev.message_at !== undefined ? `${ev.message_at}:${message}` : `${ev.session_id ?? ""}:${ev.status ?? ""}:${message}`)
          .digest("hex");
      if (!devin.seenMessageIds.includes(id)) {
        devin.seenMessageIds.push(id);
        if (devin.seenMessageIds.length > 500) devin.seenMessageIds = devin.seenMessageIds.slice(-500);
        devin.lastMessage = message.slice(0, 500);
        devin.lastMessageAt = at;
        await this.store.addComment({
          id: crypto.randomUUID(),
          ticketKey: t.key,
          author: actor,
          body: message,
          source: "devin",
          createdAt: at,
        });
        changes.push("message");
      }
    }

    const prUrl = str(ev.pr_url, 2000).trim();
    if (prUrl && prUrl !== t.prUrl) (t.prUrl = prUrl), changes.push(`PR ${prUrl}`);

    let next: Status | null = null;
    const finalStatus = ev.status ?? devin.status;
    const finished = finalStatus === "finished" || finalStatus === "done" || finalStatus === "completed";
    if (finished && t.prUrl && t.status !== "Done") next = "Done";
    else if (t.prUrl && (t.status === "Backlog" || t.status === "Ready" || t.status === "In Progress")) next = "In Review";
    else if (!t.prUrl && (ev.session_id || ev.status) && (t.status === "Backlog" || t.status === "Ready")) next = "In Progress";
    if (next && next !== t.status) {
      changes.push(`${t.status} → ${next}`);
      t.status = next;
    }

    t.devin = devin;
    if (changes.length === 0) return t;
    t.updatedAt = Date.now();
    await this.store.putTicket(t);
    await this.event(t.key, actor, "devin update", changes.join("; "));
    return t;
  }
}

export function ticketProjectKey(ticketKey: string): string {
  const pk = projectKeyOf(ticketKey.toUpperCase());
  if (!pk) throw new HttpError(400, `malformed ticket key ${ticketKey}`);
  return pk;
}
