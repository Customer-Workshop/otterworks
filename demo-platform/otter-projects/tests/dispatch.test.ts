import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { buildOutboundPayload, dispatchDevinApi, dispatchWebhook } from "@/lib/dispatch";
import { verifySignature } from "@/lib/hmac";
import { renderPrompt } from "@/lib/prompt";
import { TicketService } from "@/lib/service";
import { fetchQueue, freshStore, seedProject, seedTicket } from "./helpers";

const ENV = { ...process.env };

beforeEach(() => {
  process.env.PROJECTS_WEBHOOK_SECRET = "whsec";
  process.env.DEVIN_WEBHOOK_SECRET = "automation-secret";
  process.env.PUBLIC_URL = "https://projects.example.test/";
  process.env.DEVIN_API_KEY = "cog_test";
  process.env.DEVIN_ORG_ID = "org-123";
  process.env.LOCAL_MODE = "true";
});
afterEach(() => {
  process.env = { ...ENV };
});

describe("prompt", () => {
  it("renders the default template as one line", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    const p = await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);
    const prompt = renderPrompt(p, t);
    expect(prompt).toBe("Implement OTTER-1: Fix the thing. Line one. Line two.. Repo: org/otterworks. Acceptance criteria are in the ticket; run the relevant tests and create a PR.");
    expect(prompt).not.toMatch(/\n/);
  });
});

describe("webhook dispatcher", () => {
  it("posts a signed payload with prompt first, X-Webhook-Secret and callback_url", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    const p = await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);
    const q = fetchQueue([{ status: 200, body: { ok: true } }]);

    const res = await dispatchWebhook({ ...p, dispatcher: "webhook" }, t, { fetch: q.fn, backoffMs: 0 });
    expect(res.ok).toBe(true);
    expect(res.delivery.attempts).toBe(1);
    expect(q.calls).toHaveLength(1);
    const call = q.calls[0]!;
    expect(call.url).toBe("https://hook.test/in");
    const headers = call.init!.headers as Record<string, string>;
    const body = String(call.init!.body);
    expect(headers["X-Webhook-Secret"]).toBe("automation-secret");
    expect(verifySignature(body, headers["X-OtterProjects-Signature"], "whsec")).toBe(true);
    expect(Object.keys(JSON.parse(body))[0]).toBe("prompt");
    const payload = JSON.parse(body) as ReturnType<typeof buildOutboundPayload>;
    expect(payload.event).toBe("ticket.assigned_to_devin");
    expect(payload.callback_url).toBe("https://projects.example.test/api/webhooks/devin?ticket=OTTER-1");
    expect(payload.callback_api_key).toBe("PROJECTS_API_KEY");
    expect(payload.ticket.key).toBe("OTTER-1");
    expect(Buffer.byteLength(body)).toBeLessThan(20 * 1024);
  });

  it("retries 3x on 5xx / network errors then fails", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    const p = await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);
    const q = fetchQueue([{ status: 503 }, { status: 0, throws: "ECONNRESET" }, { status: 500 }]);
    const res = await dispatchWebhook({ ...p, dispatcher: "webhook" }, t, { fetch: q.fn, backoffMs: 0 });
    expect(res.ok).toBe(false);
    expect(res.delivery.attempts).toBe(3);
    expect(q.calls).toHaveLength(3);
    expect(res.delivery.error).toBe("HTTP 500");
  });

  it("succeeds on the second attempt", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    const p = await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);
    const q = fetchQueue([{ status: 502 }, { status: 202 }]);
    const res = await dispatchWebhook({ ...p, dispatcher: "webhook" }, t, { fetch: q.fn, backoffMs: 0 });
    expect(res.ok).toBe(true);
    expect(res.delivery.attempts).toBe(2);
  });

  it("does not retry 4xx", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    const p = await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);
    const q = fetchQueue([{ status: 401 }]);
    const res = await dispatchWebhook({ ...p, dispatcher: "webhook" }, t, { fetch: q.fn, backoffMs: 0 });
    expect(res.ok).toBe(false);
    expect(q.calls).toHaveLength(1);
  });
});

describe("devin-api dispatcher", () => {
  it("creates a session with title/tags and returns id + url", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    const p = await seedProject(svc, { dispatcher: "devin-api", createAsUserId: "google-oauth2|u1" });
    const t = await seedTicket(svc);
    const q = fetchQueue([{ status: 200, body: { session_id: "devin-xyz", url: "https://app.devin.ai/sessions/xyz", status: "new", pull_requests: [], updated_at: 1 } }]);
    const res = await dispatchDevinApi(p, t, { fetch: q.fn });
    expect(res.ok).toBe(true);
    expect(res.session).toEqual({ id: "devin-xyz", url: "https://app.devin.ai/sessions/xyz", status: "new" });
    const call = q.calls[0]!;
    expect(call.url).toBe("https://api.devin.ai/v3/organizations/org-123/sessions");
    expect((call.init!.headers as Record<string, string>).Authorization).toBe("Bearer cog_test");
    const body = JSON.parse(String(call.init!.body)) as Record<string, unknown>;
    expect(body.title).toBe("OTTER-1: Fix the thing");
    expect(body.tags).toEqual(["otter-projects", "OTTER-1"]);
    expect(body.create_as_user_id).toBe("google-oauth2|u1");
    expect(String(body.prompt)).not.toMatch(/\n/);
    expect(String(body.prompt)).toContain("https://projects.example.test/api/webhooks/devin?ticket=OTTER-1");
  });

  it("reports API errors", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    const p = await seedProject(svc, { dispatcher: "devin-api" });
    const t = await seedTicket(svc);
    const q = fetchQueue([{ status: 403, body: { detail: "forbidden" } }]);
    const res = await dispatchDevinApi(p, t, { fetch: q.fn });
    expect(res.ok).toBe(false);
    expect(res.delivery.error).toContain("forbidden");
  });
});

describe("TicketService triggers", () => {
  it("dispatches once when the devin label is added and moves to In Progress", async () => {
    const store = freshStore();
    const q = fetchQueue([{ status: 200 }]);
    const svc = new TicketService(store, { fetch: q.fn, backoffMs: 0 });
    await seedProject(svc);
    const t = await seedTicket(svc);
    const after = await svc.addLabels(t.key, ["devin"], undefined, "tester");
    expect(q.calls).toHaveLength(1);
    expect(after.status).toBe("In Progress");
    expect(after.devin.dispatcher).toBe("webhook");
    await svc.addLabels(t.key, ["extra"], undefined, "tester");
    await svc.assign(t.key, "devin", "tester");
    expect(q.calls).toHaveLength(1);
    expect(await store.listDeliveries(t.key)).toHaveLength(1);
  });

  it("dispatches when assignee becomes devin and records failure without transition", async () => {
    const store = freshStore();
    const q = fetchQueue([{ status: 500 }]);
    const svc = new TicketService(store, { fetch: q.fn, backoffMs: 0 });
    await seedProject(svc);
    const t = await seedTicket(svc);
    const after = await svc.assign(t.key, "devin", "tester");
    expect(q.calls).toHaveLength(3);
    expect(after.status).toBe("Backlog");
    const events = await store.listEvents(t.key);
    expect(events.some((e) => e.action === "devin dispatch failed")).toBe(true);
  });
});
