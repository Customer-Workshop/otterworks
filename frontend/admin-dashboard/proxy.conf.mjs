// Dev-server proxy mirroring nginx.conf: forwards /api/* to the API gateway so
// `ng serve` stays same-origin (no CORS), exactly like the production nginx image.
// Override the gateway with API_GATEWAY_URL (same knob as the client-app dev server).
export default {
  "/api": {
    target: process.env.API_GATEWAY_URL || "http://localhost:8080",
    changeOrigin: true,
  },
};
