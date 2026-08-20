/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import pkg from "./package.json" with { type: "json" };

// Dev/preview proxy forwards /api/v1/* to the API gateway (same-origin, no CORS),
// mirroring the old Next.js middleware rewrite. Production uses nginx for the same job.
const apiProxy = {
  "/api/v1": {
    target: process.env.API_GATEWAY_URL || "http://localhost:8080",
    changeOrigin: true,
  },
};
// Each portal bounded context is reached same-origin through its own /<context>-api prefix,
// and one env var per context selects which backend serves it: the extracted service by
// default, the legacy monolith (8095) on rollback. Both expose the same /api/* paths, so the
// prefix is stripped and nothing else changes. See docs/migration/traffic-routing.md.
const portalProxy = (prefix: string, target: string) => ({
  [`/${prefix}`]: {
    target,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(new RegExp(`^/${prefix}`), ""),
  },
});
const portalProxies = {
  ...portalProxy(
    "announcements-api",
    process.env.ANNOUNCEMENTS_API_URL || "http://localhost:8101",
  ),
  ...portalProxy(
    "user-preferences-api",
    process.env.USER_PREFERENCES_API_URL || "http://localhost:8102",
  ),
  ...portalProxy("feedback-api", process.env.FEEDBACK_API_URL || "http://localhost:8103"),
};
const billingProxy = {
  "/billing-api": {
    target: process.env.BILLING_SERVICE_URL || "http://localhost:12109",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/billing-api/, ""),
  },
};

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 3000,
    proxy: { ...apiProxy, ...portalProxies, ...billingProxy },
  },
  preview: {
    port: 3000,
    proxy: { ...apiProxy, ...portalProxies, ...billingProxy },
  },
  test: {
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
    globals: true,
    environment: "jsdom",
  },
});
