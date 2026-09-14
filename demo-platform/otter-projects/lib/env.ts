// Centralised, typed access to runtime configuration. Nothing here reads a
// secret's value into logs; callers only ever compare/sign with them.

export const env = {
  get localMode(): boolean {
    return process.env.LOCAL_MODE === "true";
  },
  get localStorePath(): string {
    return process.env.LOCAL_STORE_PATH || ".otter-projects.local.json";
  },
  get passcode(): string | undefined {
    return process.env.PROJECTS_PASSCODE;
  },
  get apiKey(): string | undefined {
    return process.env.PROJECTS_API_KEY;
  },
  get webhookSecret(): string | undefined {
    return process.env.PROJECTS_WEBHOOK_SECRET;
  },
  get sessionSecret(): string | undefined {
    return process.env.SESSION_SECRET;
  },
  get table(): string {
    return process.env.PROJECTS_TABLE || "otterworks-projects";
  },
  get awsRegion(): string {
    return process.env.AWS_REGION || "us-east-1";
  },
  /** Public base URL, used to build callback_url for outbound payloads. */
  get publicUrl(): string {
    return (process.env.PUBLIC_URL || "http://localhost:3000").replace(/\/+$/, "");
  },
  get devinApiKey(): string | undefined {
    return process.env.DEVIN_API_KEY;
  },
  get devinOrgId(): string | undefined {
    return process.env.DEVIN_ORG_ID;
  },
  /** Default target for the `webhook` dispatcher (a Devin Automation webhook trigger URL). */
  get devinWebhookUrl(): string | undefined {
    return process.env.DEVIN_WEBHOOK_URL;
  },
  /** Secret the Automation inbox expects in `X-Webhook-Secret`. */
  get devinWebhookSecret(): string | undefined {
    return process.env.DEVIN_WEBHOOK_SECRET;
  },
  get devinApiBase(): string {
    return (process.env.DEVIN_API_BASE || "https://api.devin.ai/v3").replace(/\/+$/, "");
  },
  get sessionTtlSeconds(): number {
    const raw = process.env.SESSION_TTL_SECONDS;
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) && n > 0 ? n : 8 * 60 * 60;
  },
} as const;
