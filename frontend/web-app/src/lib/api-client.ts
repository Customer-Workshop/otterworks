import axios from "axios";

// API calls go through Next.js rewrites (same origin) to avoid CORS issues.
// The rewrite proxy forwards /api/v1/* to the API gateway (configured via API_GATEWAY_URL env var).
export const apiClient = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("otter_access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      const url = error.config?.url || "";
      if (!url.includes("/auth/")) {
        localStorage.removeItem("otter_access_token");
        localStorage.removeItem("otter_refresh_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);
