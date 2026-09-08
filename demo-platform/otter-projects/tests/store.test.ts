import { describe, expect, it } from "vitest";
import { LocalStore } from "@/lib/store/local";
import { padNumber, projectKeyOf, ticketNumberOf } from "@/lib/store/types";
import type { Project, Ticket } from "@/lib/types";

const project: Project = {
  key: "OTTER", name: "OtterWorks", description: "", repo: "org/otterworks", promptTemplate: "",
  dispatcher: "webhook", webhookUrl: "", createAsUserId: "", createdAt: 1, updatedAt: 1,
};
function ticket(n: number, extra: Partial<Ticket> = {}): Ticket {
  return {
    key: `OTTER-${n}`, projectKey: "OTTER", number: n, title: `T${n}`, description: "", type: "task", priority: "Low",
    status: "Backlog", labels: [], assignee: "", repo: "", branch: "", prUrl: "", devin: {}, createdAt: n, updatedAt: n, ...extra,
  };
}

describe("LocalStore", () => {
  it("allocates sequential ticket numbers per project", async () => {
    const s = new LocalStore("");
    await s.putProject(project);
    expect(await s.nextTicketNumber("OTTER")).toBe(1);
    expect(await s.nextTicketNumber("OTTER")).toBe(2);
    expect(await s.nextTicketNumber("OTHER")).toBe(1);
  });

  it("round-trips tickets, comments, events, deliveries and cascades deletes", async () => {
    const s = new LocalStore("");
    await s.putProject(project);
    await s.putTicket(ticket(1));
    await s.putTicket(ticket(2, { devin: { sessionId: "devin-abc" } }));
    await s.addComment({ id: "c1", ticketKey: "OTTER-1", author: "a", body: "hi", source: "human", createdAt: 5 });
    await s.addEvent({ id: "e1", ticketKey: "OTTER-1", actor: "a", action: "created", createdAt: 5 });
    await s.addDelivery({ id: "d1", ticketKey: "OTTER-1", dispatcher: "webhook", target: "x", status: "ok", attempts: 1, createdAt: 5 });

    expect((await s.listTickets("OTTER")).map((t) => t.key)).toEqual(["OTTER-1", "OTTER-2"]);
    expect((await s.listTicketsWithSessions()).map((t) => t.key)).toEqual(["OTTER-2"]);
    expect(await s.listComments("OTTER-1")).toHaveLength(1);
    expect(await s.listEvents("OTTER-1")).toHaveLength(1);
    expect(await s.listDeliveries("OTTER-1")).toHaveLength(1);

    await s.deleteTicket(ticket(1));
    expect(await s.getTicket("OTTER-1")).toBeNull();
    expect(await s.listComments("OTTER-1")).toHaveLength(0);

    await s.deleteProject("OTTER");
    expect(await s.getProject("OTTER")).toBeNull();
    expect(await s.listTickets("OTTER")).toHaveLength(0);
  });

  it("key helpers", () => {
    expect(padNumber(7)).toBe("000007");
    expect(projectKeyOf("OTTER-7")).toBe("OTTER");
    expect(ticketNumberOf("OTTER-7")).toBe(7);
    expect(projectKeyOf("bad")).toBeNull();
  });
});
