export const TICKET_TYPES = ["story", "bug", "task"] as const;
export type TicketType = (typeof TICKET_TYPES)[number];

export const PRIORITIES = ["Low", "Medium", "High", "Critical"] as const;
export type Priority = (typeof PRIORITIES)[number];

export const STATUSES = ["Backlog", "Ready", "In Progress", "In Review", "Done"] as const;
export type Status = (typeof STATUSES)[number];

export const DISPATCHERS = ["devin-api", "webhook", "none"] as const;
export type DispatcherKind = (typeof DISPATCHERS)[number];

/** Built-in bot assignee; assigning a ticket to it triggers a Devin dispatch. */
export const DEVIN_ASSIGNEE = "devin";
/** Label that triggers a Devin dispatch. */
export const DEVIN_LABEL = "devin";

export const DEFAULT_PROMPT_TEMPLATE =
  "Implement {key}: {title}. {description}. Repo: {repo}. Acceptance criteria are in the ticket; run the relevant tests and create a PR.";

export interface Project {
  key: string;
  name: string;
  description: string;
  repo: string;
  promptTemplate: string;
  dispatcher: DispatcherKind;
  /** Target URL for the `webhook` dispatcher (e.g. a Devin Automation webhook trigger). */
  webhookUrl: string;
  /** Optional Devin user id to create sessions as (devin-api dispatcher). */
  createAsUserId: string;
  createdAt: number;
  updatedAt: number;
}

export interface DevinLink {
  sessionId?: string;
  sessionUrl?: string;
  status?: string;
  lastMessage?: string;
  lastMessageAt?: number;
  dispatcher?: DispatcherKind;
  dispatchedAt?: number;
  /** Message ids / timestamps already mirrored onto the ticket (dedup for the poller). */
  seenMessageIds?: string[];
  lastPolledAt?: number;
}

export interface Ticket {
  key: string;
  projectKey: string;
  number: number;
  title: string;
  description: string;
  type: TicketType;
  priority: Priority;
  status: Status;
  labels: string[];
  assignee: string;
  repo: string;
  branch: string;
  prUrl: string;
  devin: DevinLink;
  createdAt: number;
  updatedAt: number;
}

export type CommentSource = "human" | "devin";

export interface Comment {
  id: string;
  ticketKey: string;
  author: string;
  body: string;
  source: CommentSource;
  createdAt: number;
}

export interface ActivityEvent {
  id: string;
  ticketKey: string;
  actor: string;
  action: string;
  detail?: string;
  createdAt: number;
}

export type DeliveryStatus = "ok" | "failed";

/** Record of one outbound dispatch (webhook or devin-api) for a ticket. */
export interface WebhookDelivery {
  id: string;
  ticketKey: string;
  dispatcher: DispatcherKind;
  target: string;
  status: DeliveryStatus;
  attempts: number;
  responseStatus?: number;
  error?: string;
  createdAt: number;
}

export interface TicketDetail {
  ticket: Ticket;
  comments: Comment[];
  events: ActivityEvent[];
  deliveries: WebhookDelivery[];
}

/** Payload sent by the `webhook` dispatcher and consumed by a Devin Automation. */
export interface OutboundTicketPayload {
  /** First key on purpose: Automation webhook triggers paste the body into the prompt. */
  prompt: string;
  event: "ticket.assigned_to_devin";
  ticket: {
    key: string;
    title: string;
    description: string;
    type: TicketType;
    priority: Priority;
    status: Status;
    labels: string[];
    repo: string;
    branch: string;
    url: string;
  };
  project: { key: string; name: string; repo: string };
  callback_url: string;
  /** Name of the org secret holding the bearer token for callback_url (never the value). */
  callback_api_key: string;
  /** Stable per-dispatch id (also sent as X-OtterProjects-Delivery); identical across retries. */
  delivery_id?: string;
  callback_instructions: string;
}

/** Payload accepted by POST /api/webhooks/devin. */
export interface InboundDevinEvent {
  ticket: string;
  session_id?: string;
  session_url?: string;
  status?: string;
  message?: string;
  pr_url?: string;
}
