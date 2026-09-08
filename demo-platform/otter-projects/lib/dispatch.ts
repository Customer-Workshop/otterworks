import crypto from "node:crypto";
import { env } from "@/lib/env";
import { signBody } from "@/lib/hmac";
import { DevinClient, summarizeStatus, type FetchLike } from "@/lib/devin";
import { callbackUrl, renderPrompt } from "@/lib/prompt";
import type { OutboundTicketPayload, Project, Ticket, WebhookDelivery } from "@/lib/types";

export interface DispatchResult {
  ok: boolean;
  delivery: WebhookDelivery;
  /** Set by the devin-api dispatcher on success. */
  session?: { id: string; url: string; status: string };
  prompt: string;
}

export interface DispatchOptions {
  fetch?: FetchLike;
  /** Backoff base in ms (tests pass 0). */
  backoffMs?: number;
  now?: () => number;
}

const MAX_ATTEMPTS = 3;
const MAX_BODY_BYTES = 20 * 1024;

function sleep(ms: number): Promise<void> {
  return ms > 0 ? new Promise((r) => setTimeout(r, ms)) : Promise.resolve();
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

/**
 * Body for the `webhook` dispatcher. `prompt` is deliberately the FIRST key:
 * Devin Automation webhook triggers paste the whole body into the session
 * prompt as context, so the instruction should lead. Kept under 20KB.
 */
export function buildOutboundPayload(project: Project, ticket: Ticket, prompt: string): OutboundTicketPayload {
  const base = (descriptionMax: number, promptMax: number): OutboundTicketPayload => ({
    prompt: truncate(prompt, promptMax),
    event: "ticket.assigned_to_devin",
    ticket: {
      key: ticket.key,
      title: ticket.title,
      description: truncate(ticket.description, descriptionMax),
      type: ticket.type,
      priority: ticket.priority,
      status: ticket.status,
      labels: ticket.labels,
      repo: ticket.repo || project.repo,
      branch: ticket.branch,
      url: `${env.publicUrl}/projects/${encodeURIComponent(project.key)}/tickets/${encodeURIComponent(ticket.key)}`,
    },
    project: { key: project.key, name: project.name, repo: project.repo },
    callback_url: callbackUrl(env.publicUrl, ticket.key),
    callback_api_key: "PROJECTS_API_KEY",
    callback_instructions:
      "POST JSON {ticket, session_id, session_url, status, message, pr_url} to callback_url with header 'Authorization: Bearer <PROJECTS_API_KEY>' whenever you make progress, open a PR, or finish.",
  });
  const size = (p: OutboundTicketPayload) => Buffer.byteLength(JSON.stringify(p), "utf8");
  let descriptionMax = 12_000;
  let promptMax = 12_000;
  let payload = base(descriptionMax, promptMax);
  while (size(payload) > MAX_BODY_BYTES && (descriptionMax > 200 || promptMax > 200)) {
    descriptionMax = Math.max(200, Math.floor(descriptionMax / 2));
    promptMax = Math.max(200, Math.floor(promptMax / 2));
    payload = base(descriptionMax, promptMax);
  }
  return payload;
}

function newDelivery(ticket: Ticket, dispatcher: Project["dispatcher"], target: string, now: number): WebhookDelivery {
  return {
    id: crypto.randomUUID(),
    ticketKey: ticket.key,
    dispatcher,
    target,
    status: "failed",
    attempts: 0,
    createdAt: now,
  };
}

/** POST the signed payload to the project's webhook URL, retrying 3x with backoff. */
export async function dispatchWebhook(project: Project, ticket: Ticket, opts: DispatchOptions = {}): Promise<DispatchResult> {
  const f: FetchLike = opts.fetch ?? ((i, init) => fetch(i, init));
  const now = opts.now ?? Date.now;
  const backoff = opts.backoffMs ?? 500;
  const target = project.webhookUrl || env.devinWebhookUrl || "";
  const prompt = renderPrompt(project, ticket);
  const delivery = newDelivery(ticket, "webhook", target, now());

  if (!target) {
    delivery.error = "no webhook URL configured (project.webhookUrl or DEVIN_WEBHOOK_URL)";
    return { ok: false, delivery, prompt };
  }

  const body = JSON.stringify(buildOutboundPayload(project, ticket, prompt));
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "User-Agent": "otter-projects/1.0",
    "X-OtterProjects-Event": "ticket.assigned_to_devin",
    "X-OtterProjects-Ticket": ticket.key,
  };
  if (env.webhookSecret) headers["X-OtterProjects-Signature"] = signBody(body, env.webhookSecret);
  if (env.devinWebhookSecret) headers["X-Webhook-Secret"] = env.devinWebhookSecret;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    delivery.attempts = attempt;
    try {
      const res = await f(target, { method: "POST", headers, body });
      delivery.responseStatus = res.status;
      if (res.ok) {
        delivery.status = "ok";
        delivery.error = undefined;
        return { ok: true, delivery, prompt };
      }
      delivery.error = `HTTP ${res.status}`;
      if (res.status >= 400 && res.status < 500 && res.status !== 429) break;
    } catch (err) {
      delivery.error = err instanceof Error ? err.message : String(err);
    }
    if (attempt < MAX_ATTEMPTS) await sleep(backoff * 2 ** (attempt - 1));
  }
  return { ok: false, delivery, prompt };
}

/** Create a Devin session directly through the v3 API. */
export async function dispatchDevinApi(project: Project, ticket: Ticket, opts: DispatchOptions = {}): Promise<DispatchResult> {
  const now = opts.now ?? Date.now;
  const prompt = renderPrompt(project, ticket);
  const target = `${env.devinApiBase}/organizations/${env.devinOrgId ?? "?"}/sessions`;
  const delivery = newDelivery(ticket, "devin-api", target, now());
  delivery.attempts = 1;

  if (!env.devinApiKey || !env.devinOrgId) {
    delivery.error = "DEVIN_API_KEY / DEVIN_ORG_ID not configured";
    return { ok: false, delivery, prompt };
  }
  const client = new DevinClient({
    apiKey: env.devinApiKey,
    orgId: env.devinOrgId,
    apiBase: env.devinApiBase,
    fetch: opts.fetch,
  });
  try {
    const fullPrompt = `${prompt} When you make progress, open a PR, or finish, POST JSON {ticket:"${ticket.key}", session_id, session_url, status, message, pr_url} to ${callbackUrl(env.publicUrl, ticket.key)} with header Authorization: Bearer <PROJECTS_API_KEY> (org secret PROJECTS_API_KEY).`;
    const s = await client.createSession({
      prompt: fullPrompt,
      title: `${ticket.key}: ${ticket.title}`,
      tags: ["otter-projects", ticket.key],
      create_as_user_id: project.createAsUserId || undefined,
    });
    delivery.status = "ok";
    delivery.responseStatus = 200;
    return { ok: true, delivery, prompt, session: { id: s.session_id, url: s.url, status: summarizeStatus(s) } };
  } catch (err) {
    delivery.error = err instanceof Error ? err.message : String(err);
    return { ok: false, delivery, prompt };
  }
}

export function dispatch(project: Project, ticket: Ticket, opts: DispatchOptions = {}): Promise<DispatchResult> {
  switch (project.dispatcher) {
    case "devin-api":
      return dispatchDevinApi(project, ticket, opts);
    case "webhook":
      return dispatchWebhook(project, ticket, opts);
    default: {
      const delivery = newDelivery(ticket, "none", "", (opts.now ?? Date.now)());
      delivery.error = "project dispatcher is 'none'";
      return Promise.resolve({ ok: false, delivery, prompt: renderPrompt(project, ticket) });
    }
  }
}
