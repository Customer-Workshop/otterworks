import { env } from "@/lib/env";
import { DevinClient, summarizeStatus, type FetchLike } from "@/lib/devin";
import { TicketService } from "@/lib/service";
import { getStore } from "@/lib/store";
import type { Store } from "@/lib/store/types";

export interface PollSummary {
  polled: number;
  updated: string[];
  errors: { ticket: string; error: string }[];
  skipped?: string;
}

/**
 * Mirror Devin session status / new messages / PR URLs onto every ticket with
 * an attached session. Run by the Kubernetes CronJob (every 60s) via
 * POST /api/devin/poll, or manually.
 */
export async function pollDevinSessions(store: Store = getStore(), fetchImpl?: FetchLike): Promise<PollSummary> {
  const summary: PollSummary = { polled: 0, updated: [], errors: [] };
  if (!env.devinApiKey || !env.devinOrgId) {
    summary.skipped = "DEVIN_API_KEY / DEVIN_ORG_ID not configured";
    return summary;
  }
  const client = new DevinClient({ apiKey: env.devinApiKey, orgId: env.devinOrgId, apiBase: env.devinApiBase, fetch: fetchImpl });
  const svc = new TicketService(store);
  const tickets = await store.listTicketsWithSessions();

  for (const t of tickets) {
    const sessionId = t.devin.sessionId;
    if (!sessionId || t.status === "Done") continue;
    summary.polled += 1;
    try {
      const [session, messages] = await Promise.all([client.getSession(sessionId), client.listMessages(sessionId)]);
      const seen = new Set(t.devin.seenMessageIds ?? []);
      const fresh = messages
        .filter((m) => m.source === "devin" && !seen.has(m.event_id))
        .sort((a, b) => a.created_at - b.created_at);
      const prUrl = session.pull_requests?.[session.pull_requests.length - 1]?.url;
      const status = summarizeStatus(session);
      const before = t.updatedAt;

      for (const m of fresh) {
        await svc.applyDevinEvent({
          ticket: t.key,
          session_id: session.session_id,
          session_url: session.url,
          message: m.message,
          message_id: m.event_id,
          message_at: m.created_at,
        });
      }
      const after = await svc.applyDevinEvent({
        ticket: t.key,
        session_id: session.session_id,
        session_url: session.url,
        status,
        pr_url: prUrl,
      });
      after.devin.lastPolledAt = Date.now();
      await store.putTicket(after);
      if (after.updatedAt !== before || fresh.length > 0) summary.updated.push(t.key);
    } catch (err) {
      summary.errors.push({ ticket: t.key, error: err instanceof Error ? err.message : String(err) });
    }
  }
  return summary;
}
