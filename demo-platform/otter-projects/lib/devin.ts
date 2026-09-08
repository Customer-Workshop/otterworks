// Thin client for the Devin v3 API (https://docs.devin.ai/api-reference).
// `fetch` is injectable so dispatchers and the poller are unit-testable.

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface DevinConfig {
  apiKey: string;
  orgId: string;
  apiBase: string;
  fetch?: FetchLike;
}

export interface DevinSession {
  session_id: string;
  url: string;
  status: string;
  status_detail?: string | null;
  title?: string | null;
  pull_requests: { url: string; state?: string }[];
  updated_at: number;
}

export interface DevinMessage {
  event_id: string;
  source: "devin" | "user";
  message: string;
  created_at: number;
}

export interface CreateSessionInput {
  prompt: string;
  title: string;
  tags: string[];
  create_as_user_id?: string;
}

export class DevinApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "DevinApiError";
  }
}

export class DevinClient {
  private readonly f: FetchLike;

  constructor(private readonly cfg: DevinConfig) {
    this.f = cfg.fetch ?? ((input, init) => fetch(input, init));
  }

  private async call<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await this.f(`${this.cfg.apiBase}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.cfg.apiKey}`,
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    if (!res.ok) {
      let detail = `${res.status}`;
      try {
        const body = (await res.json()) as { detail?: string; title?: string };
        detail = body.detail || body.title || detail;
      } catch {
        /* non-JSON error body */
      }
      throw new DevinApiError(res.status, `Devin API ${path}: ${detail}`);
    }
    return (await res.json()) as T;
  }

  createSession(input: CreateSessionInput): Promise<DevinSession> {
    const body: CreateSessionInput = { prompt: input.prompt, title: input.title, tags: input.tags };
    if (input.create_as_user_id) body.create_as_user_id = input.create_as_user_id;
    return this.call<DevinSession>(`/organizations/${this.cfg.orgId}/sessions`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  getSession(sessionId: string): Promise<DevinSession> {
    return this.call<DevinSession>(`/organizations/${this.cfg.orgId}/sessions/${encodeURIComponent(sessionId)}`);
  }

  async listMessages(sessionId: string): Promise<DevinMessage[]> {
    const out: DevinMessage[] = [];
    let after: string | null = null;
    for (let page = 0; page < 20; page += 1) {
      const qs = after ? `?first=100&after=${encodeURIComponent(after)}` : "?first=100";
      const res: { items: DevinMessage[]; has_next_page?: boolean; end_cursor?: string | null } = await this.call(
        `/organizations/${this.cfg.orgId}/sessions/${encodeURIComponent(sessionId)}/messages${qs}`,
      );
      out.push(...(res.items ?? []));
      if (!res.has_next_page || !res.end_cursor) break;
      after = res.end_cursor;
    }
    return out;
  }
}

/** Map a v3 session to the short status shown on the ticket's Devin panel. */
export function summarizeStatus(s: Pick<DevinSession, "status" | "status_detail">): string {
  if (s.status === "running" && s.status_detail) return s.status_detail;
  if (s.status === "exit") return s.status_detail === "finished" ? "finished" : "exited";
  return s.status;
}
