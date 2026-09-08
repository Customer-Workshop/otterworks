/**
 * Seed the OTTER project with realistic engineering-productivity tickets.
 *
 *   LOCAL_MODE=true npm run seed          # JSON-file store
 *   PROJECTS_TABLE=otterworks-projects npm run seed   # DynamoDB (AWS creds in env)
 *
 * Idempotent: skips when OTTER already exists unless RESEED=true.
 */
import { getStore } from "@/lib/store";
import { TicketService } from "@/lib/service";
import { DEFAULT_PROMPT_TEMPLATE, type Priority, type Status, type TicketType } from "@/lib/types";

interface Seed {
  title: string;
  type: TicketType;
  priority: Priority;
  status?: Status;
  labels: string[];
  assignee?: string;
  description: string;
}

const OTTER_7: Seed = {
  title: "Document export returns 401 for an authenticated user",
  type: "bug",
  priority: "High",
  labels: ["document-service", "api-gateway"],
  description:
    "**Observed on t-main.otterworks.app**: after logging in and creating a document, `GET https://api-t-main.otterworks.app/api/v1/documents/{id}/export?format=markdown` with a valid `Authorization: Bearer <jwt>` returns `401 {\"detail\":\"Authentication required\"}`. `GET /api/v1/documents/{id}` and `POST /api/v1/documents/` succeed for the same token. Also POST /api/v1/documents/ returns 400 owner_id is required unless owner_id is passed in the body, even with a valid JWT. **Acceptance criteria**: (1) export/read/update/delete on an owned document return 2xx through the gateway with a valid JWT; (2) a document owned by another user still returns 403; (3) unauthenticated requests still return 401; (4) unit tests cover the JWT-valid, JWT-invalid-but-X-User-ID-present, and no-identity paths; (5) verified against a deployed `workshop-<id>` tenant, not just locally.",
};

const SEEDS: Seed[] = [
  {
    title: "Add request-id to gateway error responses",
    type: "story",
    priority: "Medium",
    status: "Ready",
    labels: ["api-gateway", "observability"],
    description:
      "Error responses from `services/api-gateway` (4xx/5xx) do not carry the `X-Request-ID` that the access log records, so support cannot correlate a user-reported error with a log line.\n\n**Acceptance criteria**\n- Every gateway-generated error body includes `request_id` and the `X-Request-ID` response header.\n- Upstream service errors proxied through the gateway keep the same id.\n- Covered by a Go unit test in `internal/proxy`.",
  },
  {
    title: "Flaky test in notification-service consumer",
    type: "bug",
    priority: "Medium",
    labels: ["notification-service", "flaky-test", "ci"],
    description:
      "`NotificationConsumerTest#deliversInOrder` fails roughly 1 in 8 CI runs with `expected 3 deliveries but got 2`. It passes on retry. Suspect a race between the in-memory broker and the assertion, but the fix should not just add a sleep.\n\n**Acceptance criteria**\n- Test passes 50/50 consecutive runs locally (`-Dtest.repeat=50`).\n- Root cause described in the PR.",
  },
  {
    title: "Upgrade commons-text past CVE-2022-42889 blast radius",
    type: "task",
    priority: "Critical",
    status: "Ready",
    labels: ["security", "dependencies", "jvm"],
    description:
      "`org.apache.commons:commons-text` < 1.10.0 is reachable from several JVM modules (see `make deps-inventory`). Upgrade to a non-vulnerable version everywhere it is pulled directly or transitively, and keep behaviour identical.\n\n**Acceptance criteria**\n- No module resolves a vulnerable commons-text.\n- Existing module test suites pass.\n- Advisory gate (`make advisory-gate`) is green.",
  },
  {
    title: "Search suggest should be case-insensitive",
    type: "bug",
    priority: "Low",
    labels: ["search-service"],
    description:
      "Typing `Onboarding` in the web-app search box returns suggestions, but `onboarding` returns none, even though MeiliSearch itself is case-insensitive. The suggest endpoint appears to pre-filter results before returning them.\n\n**Acceptance criteria**\n- `/api/v1/search/suggest?q=onboarding` and `?q=ONBOARDING` return the same set.\n- Unit test added for the suggest handler.",
  },
  {
    title: "Admin-service crash-loops on boot (Rails logger)",
    type: "bug",
    priority: "High",
    labels: ["admin-service", "rails"],
    description:
      "In the `t-main` tenant the `admin-service` pod restarts continuously. Container log ends with an `ArgumentError` raised from `config/environments/production.rb` while configuring the logger on Rails 7.1.\n\n**Acceptance criteria**\n- Pod reaches `Ready` and `/health` returns 200.\n- Logs are still written to stdout with tagged request ids.",
  },
  {
    title: "Web-app document list pagination drops the last page",
    type: "bug",
    priority: "Medium",
    labels: ["web-app", "document-service"],
    description:
      "With 41 documents and a page size of 20, the document list shows pages 1 and 2 only; the 41st document is unreachable from the UI. The API returns `total: 41`.\n\n**Acceptance criteria**\n- Page count is `ceil(total / pageSize)`.\n- Component test covers the boundary.",
  },
  {
    title: "Emit OpenTelemetry spans from file-service uploads",
    type: "story",
    priority: "Medium",
    labels: ["file-service", "observability"],
    description:
      "Uploads via `file-service` are invisible in traces; only the gateway span exists. Add a server span per upload with `file.size`, `file.content_type` and the S3 key prefix (not the full key).\n\n**Acceptance criteria**\n- Spans appear in the collector for a test upload.\n- No PII in span attributes.",
  },
  {
    title: "Rate-limit auth-service /login per IP",
    type: "story",
    priority: "High",
    labels: ["auth-service", "security"],
    description:
      "`POST /api/v1/auth/login` accepts unlimited attempts. Add a sliding-window limiter (Redis-backed, 10 attempts / 5 min per IP) returning `429` with `Retry-After`.\n\n**Acceptance criteria**\n- 11th attempt within the window returns 429.\n- Limiter is bypassed when `RATE_LIMIT_DISABLED=true` (tests).\n- Documented in `docs/api-contract.md`.",
  },
  {
    title: "Nightly CI: cache Gradle and npm dependencies",
    type: "task",
    priority: "Low",
    status: "Done",
    labels: ["ci"],
    description:
      "The nightly workflow re-downloads all Gradle and npm dependencies (~6 min). Add `actions/cache` keyed on lockfiles.\n\n**Acceptance criteria**\n- Nightly runtime drops by at least 4 minutes on a warm cache.",
  },
  {
    title: "Collab-service: reconnect loses unsaved cursor positions",
    type: "bug",
    priority: "Low",
    labels: ["collab-service", "web-app"],
    description:
      "When the websocket drops and reconnects, other participants' cursors disappear until they move again. The presence snapshot on reconnect does not include cursor state.\n\n**Acceptance criteria**\n- Cursor positions are restored from the presence snapshot within 1s of reconnect.",
  },
];

async function main(): Promise<void> {
  const store = getStore();
  const svc = new TicketService(store);
  const existing = await store.getProject("OTTER");
  if (existing && process.env.RESEED !== "true") {
    console.log("OTTER already exists — set RESEED=true to recreate. Nothing to do.");
    return;
  }
  if (existing) {
    console.log("RESEED=true: deleting existing OTTER project…");
    await store.deleteProject("OTTER");
  }

  await svc.createProject({
    key: "OTTER",
    name: "OtterWorks",
    description: "Engineering productivity backlog for the OtterWorks demo platform.",
    repo: "Cognition-Partner-Workshops/otterworks",
    promptTemplate: DEFAULT_PROMPT_TEMPLATE,
    dispatcher: process.env.SEED_DISPATCHER || "webhook",
    webhookUrl: process.env.SEED_WEBHOOK_URL || "",
  });

  // Ticket numbers are allocated sequentially, so OTTER-7 is the 7th created.
  const ordered: Seed[] = [...SEEDS.slice(0, 6), OTTER_7, ...SEEDS.slice(6)];
  for (const s of ordered) {
    const t = await svc.createTicket(
      "OTTER",
      { title: s.title, description: s.description, type: s.type, priority: s.priority, status: s.status ?? "Backlog", labels: s.labels, assignee: s.assignee ?? "" },
      "seed",
    );
    console.log(`${t.key.padEnd(9)} ${t.status.padEnd(12)} ${t.title}`);
  }
  const seven = await store.getTicket("OTTER-7");
  if (seven?.title !== OTTER_7.title) throw new Error("OTTER-7 did not land on the expected ticket");
  console.log("Seed complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
