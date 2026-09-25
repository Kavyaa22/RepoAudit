import axios, { isAxiosError } from "axios";
import { env } from "../config/env";
import { TOKEN_STORAGE_KEY } from "../lib/constants";
import { loadUserSettings } from "../lib/user-settings";

export const apiClient = axios.create({
  baseURL: env.apiBaseUrl,
  headers: { "Content-Type": "application/json" },
});

export function formatApiError(err: unknown): string {
  if (isAxiosError(err)) {
    const data = err.response?.data as
      | { detail?: { message?: string } | string; error?: { message?: string }; message?: string }
      | string
      | undefined;

    if (data && typeof data === "object") {
      const detail = data.detail;
      if (detail && typeof detail === "object" && detail.message) {
        return String(detail.message);
      }
      if (typeof detail === "string" && detail.trim()) return detail;
      if (data.error?.message) return String(data.error.message);
      if (data.message) return String(data.message);
    }

    if (typeof data === "string" && data.trim()) return data;

    const status = err.response?.status;
    if (status === 404) {
      return (
        "API not found (404). The backend service is missing or BACKEND_URL is wrong on Railway. " +
        "Redeploy the backend and update BACKEND_URL on the frontend service."
      );
    }
    if (status === 502 || status === 503) {
      return (
        "Backend unavailable. Redeploy the backend service on Railway and confirm " +
        "/api/v1/health returns status ok."
      );
    }
    if (status === 401) {
      return "Invalid email or password.";
    }
    if (err.message?.includes("ERR_CONTENT_DECODING_FAILED") || err.code === "ERR_CONTENT_DECODING_FAILED") {
      return "API response could not be decoded. Redeploy the frontend service (proxy fix).";
    }
    if (err.message === "Network Error") {
      return (
        "Network error — could not reach the API. Confirm BACKEND_URL on the frontend " +
        "Railway service and that the backend /api/v1/health endpoint returns ok."
      );
    }
    if (err.message) return err.message;
  }

  if (err instanceof Error && err.message) return err.message;
  return "Request failed";
}

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const settings = loadUserSettings();
  if (settings.openrouterApiKey) config.headers["x-api-key"] = settings.openrouterApiKey;
  if (settings.model) config.headers["x-model"] = settings.model;
  return config;
});

apiClient.interceptors.response.use(
  (res) => {
    const ct = String(res.headers["content-type"] || "");
    if (ct.includes("text/html")) {
      return Promise.reject(
        new Error(
          "API request returned a web page instead of JSON. Set BACKEND_URL on the frontend Railway service and redeploy."
        )
      );
    }
    return res;
  },
  (err) => {
    if (isAxiosError(err) && err.response?.status === 401) {
      const url = String(err.config?.url || "");
      const data = err.response?.data as
        | { detail?: { message?: string; code?: string } | string; error?: { message?: string }; message?: string }
        | undefined;
      const detailStr =
        typeof data?.detail === "string"
          ? data.detail.toLowerCase()
          : typeof data?.detail === "object" && data.detail?.message
          ? String(data.detail.message).toLowerCase()
          : "";

      // Only redirect to login if the APP's auth token itself is expired or invalid
      const isAuthSessionExpired =
        detailStr.includes("invalid or expired token") ||
        detailStr.includes("not authenticated") ||
        detailStr.includes("invalid token");

      if (isAuthSessionExpired && !url.includes("/auth/login") && !url.includes("/auth/register")) {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        if (!window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/register")) {
          window.location.href = "/login?reason=expired";
        }
      }
    }
    return Promise.reject(new Error(formatApiError(err)));
  }
);
