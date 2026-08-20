// Announcements is served by the extracted announcements-service.
// The browser always talks same-origin to the `/announcements-api` proxy (Vite in
// dev/preview, nginx in production), whose target is selected by the ANNOUNCEMENTS_API_URL env
// var — see docs/migration/traffic-routing.md; VITE_ANNOUNCEMENTS_API_URL overrides the whole
// base URL for builds that have no same-origin proxy (native/desktop shells).
export const ANNOUNCEMENTS_BASE_URL =
  import.meta.env.VITE_ANNOUNCEMENTS_API_URL ||
  `${window.location.origin}/announcements-api`;

export const TITLE_MAX_LENGTH = 200;
export const BODY_MAX_LENGTH = 4000;

export type Announcement = {
  id: number;
  title: string;
  body: string;
  published: boolean;
  createdAt: string;
};

export type NewAnnouncement = {
  title: string;
  body: string;
  published: boolean;
};

export class AnnouncementsApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

// The portal has two error envelopes: the legacy `{error, message}` one for anything that
// reaches its exception handler, and Spring's default `{timestamp, status, error, path}`,
// which carries no `message` at all — so validation failures only ever yield `error`.
async function toApiError(response: Response): Promise<AnnouncementsApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const envelope = body as { error?: unknown; message?: unknown } | null;
  const message =
    typeof envelope?.message === "string" && envelope.message.length > 0
      ? envelope.message
      : typeof envelope?.error === "string" && envelope.error.length > 0
        ? envelope.error
        : `Announcements service returned ${response.status}`;
  return new AnnouncementsApiError(message, response.status);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${ANNOUNCEMENTS_BASE_URL}${path}`, options);
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json() as Promise<T>;
}

export const announcementsApi = {
  list: (publishedOnly: boolean) =>
    request<Announcement[]>(`/api/announcements?publishedOnly=${publishedOnly}`),
  create: (announcement: NewAnnouncement) =>
    request<Announcement>("/api/announcements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(announcement),
    }),
  publish: (id: number) =>
    request<Announcement>(`/api/announcements/${id}/publish`, { method: "POST" }),
};
