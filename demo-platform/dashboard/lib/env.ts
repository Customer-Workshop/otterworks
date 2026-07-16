// Centralised, typed access to runtime configuration. Nothing here reads a
// secret's value into logs; callers only ever compare/sign with them.

export const env = {
  get dashboardPasscode(): string | undefined {
    return process.env.DASHBOARD_PASSCODE;
  },
  get sessionSecret(): string | undefined {
    return process.env.SESSION_SECRET;
  },
  get controlTable(): string {
    return process.env.CONTROL_TABLE || "otterworks-demo-control";
  },
  get awsRegion(): string {
    return process.env.AWS_REGION || "us-east-1";
  },
  get eksCluster(): string {
    return process.env.EKS_CLUSTER || "otterworks-dev";
  },
  get platformNamespace(): string {
    return process.env.PLATFORM_NAMESPACE || "otterworks-platform";
  },
  get runnerImage(): string | undefined {
    return process.env.RUNNER_IMAGE;
  },
  get serviceAccount(): string {
    return process.env.DASHBOARD_SERVICE_ACCOUNT || "demo-ops-dashboard";
  },
  // Secret (K8s) that the runner Job references via env valueFrom — never
  // passed on argv. Its keys hold DB_PASSWORD / AWS creds etc.
  get runnerSecretName(): string {
    return process.env.RUNNER_SECRET_NAME || "demo-ops-dashboard";
  },
  get hostSuffix(): string {
    return process.env.HOST_SUFFIX || "demo.otterworks.xyz";
  },
  get sessionTtlSeconds(): number {
    const raw = process.env.SESSION_TTL_SECONDS;
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) && n > 0 ? n : 8 * 60 * 60; // ~8h
  },
} as const;

export const TENANT_LABEL = "demo/tenant";
export const TTL_LABEL = "demo/expires-at";
