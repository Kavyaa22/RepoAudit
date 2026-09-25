/** Vite env configuration (VITE_* only). Runtime override is injected by server.mjs. */

function runtimeApiBaseUrl(): string | undefined {
  if (typeof window === "undefined") return undefined;
  const value = (window as Window & { __REPOAUDIT_API_BASE_URL__?: string })
    .__REPOAUDIT_API_BASE_URL__;
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export const env = {
  apiBaseUrl: runtimeApiBaseUrl() ?? import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL ?? "",
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY ?? "",
  authDisabled: import.meta.env.VITE_AUTH_DISABLED === "true",
} as const;
