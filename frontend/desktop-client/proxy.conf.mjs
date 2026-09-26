// Dev-server proxy mirroring the admin dashboard: forwards /api/* to the API gateway so
// `ng serve` stays same-origin (no CORS). Override the gateway with API_GATEWAY_URL.
export default {
  "/api": {
    target: process.env.API_GATEWAY_URL || "http://localhost:8080",
    changeOrigin: true,
  },
};
