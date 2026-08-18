// Dev-server proxy mirroring nginx.conf: forwards /api/* to the API gateway so
// `ng serve` stays same-origin (no CORS), exactly like the production nginx image.
// Override the gateway with API_GATEWAY_URL (same knob as the client-app dev server).
export default {
  "/api": {
    target: process.env.API_GATEWAY_URL || "http://localhost:8080",
    changeOrigin: true,
  },
  // Billing report backend: whichever estate serves the billing report
  // contract. Defaults to the legacy billing app (make procs-up).
  "/billing-api": {
    target: process.env.BILLING_REPORT_API_URL || "http://localhost:8096",
    changeOrigin: true,
    pathRewrite: { "^/billing-api": "" },
  },
};
