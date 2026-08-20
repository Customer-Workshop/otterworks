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
// The announcements slice talks same-origin to /announcements-api; ANNOUNCEMENTS_API_URL
// selects which portal backend serves it — the legacy monolith (8095) today, the extracted
// announcements-service (8101) after the cut. Both expose the same /api/announcements paths.
const announcementsProxy = {
  "/announcements-api": {
    target: process.env.ANNOUNCEMENTS_API_URL || "http://localhost:8095",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/announcements-api/, ""),
  },
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
    proxy: { ...apiProxy, ...announcementsProxy, ...billingProxy },
  },
  preview: {
    port: 3000,
    proxy: { ...apiProxy, ...announcementsProxy, ...billingProxy },
  },
  test: {
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
    globals: true,
    environment: "jsdom",
  },
});
