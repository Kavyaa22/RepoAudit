import { cachePeek, cacheSet } from "../lib/client-cache";
import { apiClient } from "./api-client";

export type HealthResponse = {
  status: string;
  version: string;
  auth_disabled?: boolean;
  supabase?: boolean;
};

export function getCachedHealth(): HealthResponse | null {
  return cachePeek<HealthResponse>("health");
}

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>("/health");
  cacheSet("health", data);
  return data;
}
