import { env } from "@/lib/env";
import { DynamoStore } from "./dynamo";
import { LocalStore } from "./local";
import type { Store } from "./types";

// One store per process. Kept on globalThis so Next's dev-mode module
// re-evaluation does not create competing in-memory copies in LOCAL_MODE.
const g = globalThis as unknown as { __otterProjectsStore?: Store };

export function getStore(): Store {
  if (!g.__otterProjectsStore) {
    g.__otterProjectsStore = env.localMode
      ? new LocalStore(env.localStorePath)
      : new DynamoStore(env.table, env.awsRegion);
  }
  return g.__otterProjectsStore;
}

/** Test hook: swap the process-wide store. */
export function setStore(store: Store): void {
  g.__otterProjectsStore = store;
}

export type { Store } from "./types";
