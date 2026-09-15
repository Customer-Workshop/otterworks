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
// The dev/preview proxy stands in for the API gateway on the local billing fixture.
// Set BILLING_SERVICE_TOKEN to the stack's BILLING_SVC_SERVICE_TOKEN; without it the
// billing screens get 401 from the service.
const billingServiceToken = process.env.BILLING_SERVICE_TOKEN;
const billingProxy = {
  "/billing-api": {
    target: process.env.BILLING_SERVICE_URL || "http://localhost:12109",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/billing-api/, ""),
    ...(billingServiceToken
      ? { headers: { Authorization: `Bearer ${billingServiceToken}` } }
      : {}),
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
    proxy: { ...apiProxy, ...billingProxy },
  },
  preview: {
    port: 3000,
    proxy: { ...apiProxy, ...billingProxy },
  },
  test: {
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
    globals: true,
    environment: "jsdom",
  },
});
