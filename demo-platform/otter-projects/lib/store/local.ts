import fs from "node:fs";
import path from "node:path";
import type { ActivityEvent, Comment, Project, Ticket, WebhookDelivery } from "@/lib/types";
import type { Store } from "./types";

interface LocalData {
  projects: Record<string, Project>;
  counters: Record<string, number>;
  tickets: Record<string, Ticket>;
  comments: Comment[];
  events: ActivityEvent[];
  deliveries: WebhookDelivery[];
}

function empty(): LocalData {
  return { projects: {}, counters: {}, tickets: {}, comments: [], events: [], deliveries: [] };
}

/**
 * JSON-file backed store for LOCAL_MODE (`npm run dev` with no AWS). Every
 * mutation is written through to disk so state survives dev-server restarts;
 * pass `filePath = ""` for a purely in-memory store (tests).
 */
export class LocalStore implements Store {
  private data: LocalData;

  constructor(private readonly filePath: string) {
    this.data = empty();
    if (filePath && fs.existsSync(filePath)) {
      try {
        this.data = { ...empty(), ...(JSON.parse(fs.readFileSync(filePath, "utf8")) as LocalData) };
      } catch {
        this.data = empty();
      }
    }
  }

  private flush(): void {
    if (!this.filePath) return;
    fs.mkdirSync(path.dirname(path.resolve(this.filePath)), { recursive: true });
    const tmp = `${this.filePath}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this.data, null, 2));
    fs.renameSync(tmp, this.filePath);
  }

  async listProjects(): Promise<Project[]> {
    return Object.values(this.data.projects)
      .map(clone)
      .sort((a, b) => a.key.localeCompare(b.key));
  }
  async getProject(key: string): Promise<Project | null> {
    return clone(this.data.projects[key]) ?? null;
  }
  async putProject(project: Project): Promise<void> {
    this.data.projects[project.key] = clone(project);
    this.flush();
  }
  async createProject(project: Project): Promise<boolean> {
    if (this.data.projects[project.key]) return false;
    this.data.projects[project.key] = clone(project);
    this.flush();
    return true;
  }
  async deleteProject(key: string): Promise<void> {
    delete this.data.projects[key];
    delete this.data.counters[key];
    for (const t of Object.values(this.data.tickets)) {
      if (t.projectKey === key) await this.deleteTicket(t);
    }
    this.flush();
  }

  async nextTicketNumber(projectKey: string): Promise<number> {
    const n = (this.data.counters[projectKey] ?? 0) + 1;
    this.data.counters[projectKey] = n;
    this.flush();
    return n;
  }
  async listTickets(projectKey: string): Promise<Ticket[]> {
    return Object.values(this.data.tickets)
      .filter((t) => t.projectKey === projectKey)
      .map(clone)
      .sort((a, b) => a.number - b.number);
  }
  async listTicketsWithSessions(): Promise<Ticket[]> {
    return Object.values(this.data.tickets)
      .filter((t) => Boolean(t.devin.sessionId))
      .map(clone);
  }
  async getTicket(key: string): Promise<Ticket | null> {
    return clone(this.data.tickets[key]) ?? null;
  }
  async putTicket(ticket: Ticket): Promise<void> {
    this.data.tickets[ticket.key] = clone(ticket);
    this.flush();
  }
  async claimDispatch(ticketKey: string, at: number): Promise<boolean> {
    const t = this.data.tickets[ticketKey];
    if (!t || t.devin.sessionId || t.devin.dispatchedAt) return false;
    t.devin = { ...t.devin, dispatchedAt: at };
    this.flush();
    return true;
  }
  async deleteTicket(ticket: Ticket): Promise<void> {
    delete this.data.tickets[ticket.key];
    this.data.comments = this.data.comments.filter((c) => c.ticketKey !== ticket.key);
    this.data.events = this.data.events.filter((e) => e.ticketKey !== ticket.key);
    this.data.deliveries = this.data.deliveries.filter((d) => d.ticketKey !== ticket.key);
    this.flush();
  }

  async listComments(ticketKey: string): Promise<Comment[]> {
    return this.data.comments.filter((c) => c.ticketKey === ticketKey).sort(byCreated);
  }
  async addComment(comment: Comment): Promise<void> {
    this.data.comments.push(comment);
    this.flush();
  }

  async listEvents(ticketKey: string): Promise<ActivityEvent[]> {
    return this.data.events.filter((e) => e.ticketKey === ticketKey).sort(byCreated);
  }
  async addEvent(event: ActivityEvent): Promise<void> {
    this.data.events.push(event);
    this.flush();
  }

  async listDeliveries(ticketKey: string): Promise<WebhookDelivery[]> {
    return this.data.deliveries.filter((d) => d.ticketKey === ticketKey).sort(byCreated);
  }
  async addDelivery(delivery: WebhookDelivery): Promise<void> {
    this.data.deliveries.push(delivery);
    this.flush();
  }
}

/** Callers get detached copies, matching the remote store's semantics. */
function clone<T>(v: T): T {
  return v === undefined || v === null ? v : (JSON.parse(JSON.stringify(v)) as T);
}

function byCreated(a: { createdAt: number }, b: { createdAt: number }): number {
  return a.createdAt - b.createdAt;
}
