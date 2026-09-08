import type { ActivityEvent, Comment, Project, Ticket, WebhookDelivery } from "@/lib/types";

/**
 * Persistence contract. Two implementations: DynamoDB (single table
 * `otterworks-projects`) and a JSON-file store for LOCAL_MODE.
 *
 * Single-table layout (DynamoDB):
 *   PK=PROJECT#<key>   SK=META                      project
 *   PK=PROJECT#<key>   SK=COUNTER                   { n } atomic ticket counter
 *   PK=PROJECT#<key>   SK=TICKET#<zero-padded n>    ticket
 *   PK=TICKET#<key>    SK=COMMENT#<ts>#<id>         comment
 *   PK=TICKET#<key>    SK=EVENT#<ts>#<id>           activity event
 *   PK=TICKET#<key>    SK=WEBHOOK#<ts>#<id>         outbound delivery record
 */
export interface Store {
  listProjects(): Promise<Project[]>;
  getProject(key: string): Promise<Project | null>;
  putProject(project: Project): Promise<void>;
  /** Insert only if the key is free; false when it already exists. */
  createProject(project: Project): Promise<boolean>;
  deleteProject(key: string): Promise<void>;

  /** Atomically allocate the next ticket number for a project. */
  nextTicketNumber(projectKey: string): Promise<number>;
  listTickets(projectKey: string): Promise<Ticket[]>;
  /** Tickets with an attached Devin session (poller input). */
  listTicketsWithSessions(): Promise<Ticket[]>;
  getTicket(key: string): Promise<Ticket | null>;
  putTicket(ticket: Ticket): Promise<void>;
  /**
   * Atomically mark a ticket as being dispatched to Devin. Returns false when
   * another caller already claimed it (or a session is attached), so only one
   * outbound dispatch happens per assignment.
   */
  claimDispatch(ticketKey: string, at: number): Promise<boolean>;
  deleteTicket(ticket: Ticket): Promise<void>;

  listComments(ticketKey: string): Promise<Comment[]>;
  addComment(comment: Comment): Promise<void>;

  listEvents(ticketKey: string): Promise<ActivityEvent[]>;
  addEvent(event: ActivityEvent): Promise<void>;

  listDeliveries(ticketKey: string): Promise<WebhookDelivery[]>;
  addDelivery(delivery: WebhookDelivery): Promise<void>;
}

export function padNumber(n: number): string {
  return String(n).padStart(6, "0");
}

/** `OTTER-7` -> `OTTER`; null when malformed. */
export function projectKeyOf(ticketKey: string): string | null {
  const m = /^([A-Z][A-Z0-9]*)-(\d+)$/.exec(ticketKey);
  return m ? m[1]! : null;
}

export function ticketNumberOf(ticketKey: string): number | null {
  const m = /^[A-Z][A-Z0-9]*-(\d+)$/.exec(ticketKey);
  return m ? Number(m[1]) : null;
}
