import * as k8s from "@kubernetes/client-node";
import { batch } from "@/lib/k8s";
import { env } from "@/lib/env";

export type RunnerAction = "deploy" | "teardown" | "inject";

export interface RunnerJobInput {
  action: RunnerAction;
  tenantId: string;
  branch?: string;
  tier?: string;
  imageTag?: string;
  ttl?: string;
  scenario?: string;
  hostSuffix?: string;
}

// Secret keys the runner needs at runtime. These are referenced via
// envFrom/valueFrom (never placed on argv) so the passcode / DB password / AWS
// creds are not exposed in the Job spec's command line.
const RUNNER_SECRET_ENV_KEYS = ["DB_PASSWORD", "JWT_SECRET", "SECRET_KEY_BASE"] as const;

function jobName(action: RunnerAction, id: string, epoch: number): string {
  // Contract: deploy-<id>-<epoch> / teardown-<id>-<epoch>; inject uses inject-bug.
  const prefix = action === "inject" ? "inject-bug" : action;
  return `${prefix}-${id}-${epoch}`;
}

export function jobNamePrefixes(id: string): string[] {
  return [`deploy-${id}-`, `teardown-${id}-`, `inject-bug-${id}-`];
}

function scriptCommand(input: RunnerJobInput): string[] {
  const id = input.tenantId;
  switch (input.action) {
    case "deploy": {
      const args = ["scripts/deploy-tenant.sh", id, "--tier", input.tier ?? "A"];
      if (input.imageTag) args.push("--image-tag", input.imageTag);
      args.push("--ttl", input.ttl ?? "8h");
      args.push("--host-suffix", input.hostSuffix ?? env.hostSuffix);
      return args;
    }
    case "teardown":
      return ["scripts/teardown-tenant.sh", id];
    case "inject":
      return ["scripts/inject-bug.sh", id, input.scenario ?? "reset"];
  }
}

function buildEnv(input: RunnerJobInput): k8s.V1EnvVar[] {
  const plain: k8s.V1EnvVar[] = [
    { name: "CONTROL_TABLE", value: env.controlTable },
    { name: "AWS_REGION", value: env.awsRegion },
    { name: "TENANT_ID", value: input.tenantId },
  ];
  if (input.branch) plain.push({ name: "TENANT_BRANCH", value: input.branch });
  if (input.tier) plain.push({ name: "TENANT_TIER", value: input.tier });
  if (input.imageTag) plain.push({ name: "IMAGE_TAG", value: input.imageTag });
  if (input.ttl) plain.push({ name: "TTL", value: input.ttl });
  if (input.scenario) plain.push({ name: "SCENARIO", value: input.scenario });

  // Secrets injected by reference — values never appear in the Job manifest.
  const secretEnv: k8s.V1EnvVar[] = RUNNER_SECRET_ENV_KEYS.map((key) => ({
    name: key,
    valueFrom: {
      secretKeyRef: { name: env.runnerSecretName, key, optional: true },
    },
  }));

  return [...plain, ...secretEnv];
}

/** Build the Job manifest (pure — testable without a cluster). */
export function buildRunnerJob(input: RunnerJobInput, epoch: number): k8s.V1Job {
  const image = env.runnerImage;
  if (!image) throw new Error("RUNNER_IMAGE is not configured");
  const name = jobName(input.action, input.tenantId, epoch);

  return {
    apiVersion: "batch/v1",
    kind: "Job",
    metadata: {
      name,
      namespace: env.platformNamespace,
      labels: {
        "app.kubernetes.io/managed-by": "demo-ops-dashboard",
        "demo/action": input.action,
        "demo/tenant-id": input.tenantId,
      },
    },
    spec: {
      backoffLimit: 1,
      ttlSecondsAfterFinished: 3600,
      template: {
        metadata: {
          labels: {
            "app.kubernetes.io/managed-by": "demo-ops-dashboard",
            "demo/action": input.action,
          },
        },
        spec: {
          serviceAccountName: env.serviceAccount,
          restartPolicy: "Never",
          containers: [
            {
              name: "runner",
              image,
              command: scriptCommand(input),
              env: buildEnv(input),
            },
          ],
        },
      },
    },
  };
}

/** Create the runner Job in the platform namespace. Returns the Job name. */
export async function createRunnerJob(input: RunnerJobInput): Promise<string> {
  const epoch = Date.now();
  const job = buildRunnerJob(input, epoch);
  await batch().createNamespacedJob(env.platformNamespace, job);
  return job.metadata?.name ?? jobName(input.action, input.tenantId, epoch);
}
