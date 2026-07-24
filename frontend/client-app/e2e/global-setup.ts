import { chromium, request, type FullConfig } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

/**
 * Authenticated storage state used by every e2e spec.  The client-app guards
 * its in-app pages behind a JWT stored in localStorage, so without this the
 * app redirects to /login and page-level assertions can never run.
 */
export const STORAGE_STATE = "e2e/.auth/state.json";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";
const API_BASE =
  process.env.E2E_API_BASE || "http://localhost:8080/api/v1/auth";
const TEST_USER = {
  displayName: "E2E User",
  email: process.env.E2E_EMAIL || "e2e-user@otterworks.dev",
  password: process.env.E2E_PASSWORD || "Passw0rd!23",
};

interface Tokens {
  accessToken: string;
  refreshToken: string;
}

/** Log in, registering the test user first if it doesn't exist yet. */
async function fetchTokens(): Promise<Tokens> {
  const api = await request.newContext();
  try {
    const login = await api.post(`${API_BASE}/login`, {
      data: { email: TEST_USER.email, password: TEST_USER.password },
    });
    if (login.ok()) return (await login.json()) as Tokens;

    const register = await api.post(`${API_BASE}/register`, { data: TEST_USER });
    if (register.ok()) return (await register.json()) as Tokens;

    throw new Error(
      `Unable to obtain auth tokens (login ${login.status()}, register ${register.status()}). ` +
        `Is the backend running? Try: make up seed=1`
    );
  } finally {
    await api.dispose();
  }
}

export default async function globalSetup(_config: FullConfig) {
  const { accessToken, refreshToken } = await fetchTokens();

  const browser = await chromium.launch();
  const page = await browser.newPage();
  // Visit the app origin so localStorage is scoped correctly, then persist the
  // tokens exactly as the login flow does.
  await page.goto(BASE_URL);
  await page.evaluate(
    ([access, refresh]) => {
      localStorage.setItem("otter_access_token", access);
      localStorage.setItem("otter_refresh_token", refresh);
    },
    [accessToken, refreshToken]
  );

  mkdirSync(dirname(STORAGE_STATE), { recursive: true });
  await page.context().storageState({ path: STORAGE_STATE });
  await browser.close();
}
