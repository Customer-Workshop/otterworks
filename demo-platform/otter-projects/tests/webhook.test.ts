import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "@/app/api/webhooks/devin/route";
import { signBody } from "@/lib/hmac";
import { TicketService } from "@/lib/service";
import { freshStore, seedProject, seedTicket } from "./helpers";

const ENV = { ...process.env };
beforeEach(() => {
  process.env.LOCAL_MODE = "true";
  process.env.PROJECTS_API_KEY = "api-key-1";
  process.env.PROJECTS_WEBHOOK_SECRET = "whsec";
});
afterEach(() => {
  process.env = { ...ENV };
});

function post(body: unknown, headers: Record<string, string>, query = "") {
  const raw = JSON.stringify(body);
  return POST(new NextRequest(`http://localhost/api/webhooks/devin${query}`, { method: "POST", body: raw, headers }));
}

describe("POST /api/webhooks/devin", () => {
  it("rejects unauthenticated and bad-signature requests", async () => {
    freshStore();
    expect((await post({ ticket: "OTTER-1" }, {})).status).toBe(401);
    expect((await post({ ticket: "OTTER-1" }, { authorization: "Bearer nope" })).status).toBe(401);
    expect((await post({ ticket: "OTTER-1" }, { "x-otterprojects-signature": "sha256=00" })).status).toBe(401);
  });

  it("adds a Devin comment, attaches the session and moves to In Progress (API key)", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);
    const res = await post(
      { ticket: t.key, session_id: "devin-1", session_url: "https://app.devin.ai/sessions/1", status: "working", message: "Cloning the repo…" },
      { authorization: "Bearer api-key-1" },
    );
    expect(res.status).toBe(200);
    const after = (await res.json()) as { ticket: { status: string; devin: { sessionId: string; lastMessage: string } } };
    expect(after.ticket.status).toBe("In Progress");
    expect(after.ticket.devin.sessionId).toBe("devin-1");
    expect(after.ticket.devin.lastMessage).toBe("Cloning the repo…");
    const comments = await store.listComments(t.key);
    expect(comments).toHaveLength(1);
    expect(comments[0]!.source).toBe("devin");
    expect(comments[0]!.body).toBe("Cloning the repo…");
  });

  it("accepts HMAC auth, ticket from query, PR -> In Review, finished+PR -> Done, dedups messages", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);

    const b1 = { session_id: "devin-1", status: "working", message: "Opened a PR", pr_url: "https://github.com/org/otterworks/pull/42", message_id: "m1" };
    const r1 = await post(b1, { "x-otterprojects-signature": signBody(JSON.stringify(b1), "whsec") }, `?ticket=${t.key}`);
    expect(r1.status).toBe(200);
    let cur = await store.getTicket(t.key);
    expect(cur!.status).toBe("In Review");
    expect(cur!.prUrl).toBe("https://github.com/org/otterworks/pull/42");

    // Same message id again -> no new comment.
    await post(b1, { "x-otterprojects-signature": signBody(JSON.stringify(b1), "whsec") }, `?ticket=${t.key}`);
    expect(await store.listComments(t.key)).toHaveLength(1);

    // Replay without message_id is also deduplicated.
    const b1b = { session_id: "devin-1", status: "working", message: "Still on it" };
    for (let i = 0; i < 2; i += 1) await post(b1b, { authorization: "Bearer api-key-1" }, `?ticket=${t.key}`);
    expect(await store.listComments(t.key)).toHaveLength(2);

    const b2 = { session_id: "devin-1", status: "finished", message: "All done." };
    const r2 = await post(b2, { "x-otterprojects-signature": signBody(JSON.stringify(b2), "whsec") }, `?ticket=${t.key}`);
    expect(r2.status).toBe(200);
    cur = await store.getTicket(t.key);
    expect(cur!.status).toBe("Done");
    expect(await store.listComments(t.key)).toHaveLength(3);
  });

  it("persists a session URL that arrives alone", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);
    const res = await post({ ticket: t.key, session_url: "https://app.devin.ai/sessions/9" }, { authorization: "Bearer api-key-1" });
    expect(res.status).toBe(200);
    expect((await store.getTicket(t.key))!.devin.sessionUrl).toBe("https://app.devin.ai/sessions/9");
  });

  it("moves to Done when the PR arrives after a finished status", async () => {
    const store = freshStore();
    const svc = new TicketService(store);
    await seedProject(svc, { dispatcher: "none" });
    const t = await seedTicket(svc);
    await post({ ticket: t.key, session_id: "devin-1", status: "finished", message: "Done, PR incoming" }, { authorization: "Bearer api-key-1" });
    await post({ ticket: t.key, pr_url: "https://github.com/org/otterworks/pull/7" }, { authorization: "Bearer api-key-1" });
    expect((await store.getTicket(t.key))!.status).toBe("Done");
  });

  it("404s for unknown tickets and 400s without a ticket", async () => {
    freshStore();
    expect((await post({ ticket: "NOPE-1", status: "working" }, { authorization: "Bearer api-key-1" })).status).toBe(404);
    expect((await post({ status: "working" }, { authorization: "Bearer api-key-1" })).status).toBe(400);
  });
});
