import { cachePeek, cacheSet } from "../lib/client-cache";
import { rejectDemos } from "../lib/demo-filter";
import { apiClient } from "./api-client";

export type ProjectSummary = {
  project_id: string;
  display_name: string;
  repository_url: string;
  status: string;
  owner?: string | null;
  repository_name?: string | null;
  default_branch?: string | null;
  workspace_path?: string | null;
  private?: boolean;
  file_count?: number;
  audit_project_id?: string | null;
};

type Envelope<T> = { success: boolean; data: T };

export function getCachedProjects(): ProjectSummary[] {
  return rejectDemos(cachePeek<ProjectSummary[]>("projects") ?? []);
}

export async function listProjects(): Promise<ProjectSummary[]> {
  try {
    const { data } = await apiClient.get<Envelope<{ items: ProjectSummary[] }>>("/projects");
    const items = rejectDemos(data.data.items);
    cacheSet("projects", items);
    return items;
  } catch (err) {
    const cached = getCachedProjects();
    if (cached.length > 0) return cached;
    throw err;
  }
}
