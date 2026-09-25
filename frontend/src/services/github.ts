import { apiClient } from "./api-client";
import { cacheGet, cachePeek, cacheRemove, cacheRemovePrefix, cacheSet } from "../lib/client-cache";
import { rejectDemos } from "../lib/demo-filter";
import { getActiveUserId } from "../lib/user-settings";

export type GitHubStatus = {
  connected: boolean;
  github_login?: string | null;
  github_user_id?: number | null;
  scopes?: string | null;
  avatar_url?: string | null;
  connected_at?: string | null;
  last_validated_at?: string | null;
  message?: string;
};

export type GitHubRepo = {
  id: number;
  full_name: string;
  name: string;
  owner: string;
  private: boolean;
  description: string | null;
  default_branch: string;
  html_url: string;
  clone_url: string;
  language: string | null;
  updated_at: string | null;
};

export type GitHubBranch = {
  name: string;
  protected: boolean;
  commit_sha: string | null;
};

export type ImportResult = {
  project_id: string;
  display_name: string;
  repository_url: string;
  owner: string;
  repository_name: string;
  branch: string;
  workspace_path: string;
  status: string;
  private: boolean;
  file_count: number;
  message: string;
};

type Envelope<T> = { success: boolean; data: T };

const GITHUB_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

function statusCacheKey(): string {
  return `github_status:${getActiveUserId() || "anon"}`;
}

function reposCacheKey(): string {
  return `github_repos:${getActiveUserId() || "anon"}`;
}

function countCacheKey(): string {
  return `github_repo_count:${getActiveUserId() || "anon"}`;
}

export function clearGitHubCache(): void {
  cacheRemovePrefix("github_");
}

function branchesCacheKey(owner: string, repo: string): string {
  return `github_branches:${getActiveUserId() || "anon"}:${owner}/${repo}`;
}

export function getCachedGitHubStatus(): GitHubStatus | null {
  if (!getActiveUserId()) return null;
  return cachePeek<GitHubStatus>(statusCacheKey()) ?? cacheGet<GitHubStatus>(statusCacheKey(), GITHUB_CACHE_TTL_MS);
}

export function getCachedGitHubRepos(): GitHubRepo[] | null {
  if (!getActiveUserId()) return null;
  const status = getCachedGitHubStatus();
  if (status && !status.connected) return [];
  const items =
    cachePeek<GitHubRepo[]>(reposCacheKey()) ?? cacheGet<GitHubRepo[]>(reposCacheKey(), GITHUB_CACHE_TTL_MS);
  return items ? rejectDemos(items) : null;
}

export function getCachedGitHubRepoCount(): number | null {
  if (!getActiveUserId()) return null;
  const status = getCachedGitHubStatus();
  if (status && !status.connected) return 0;
  return cachePeek<number>(countCacheKey()) ?? cacheGet<number>(countCacheKey(), GITHUB_CACHE_TTL_MS);
}

export function getCachedGitHubBranches(
  owner: string,
  repo: string,
): { items: GitHubBranch[]; default_branch: string | null } | null {
  return cachePeek(branchesCacheKey(owner, repo));
}

function persistStatus(status: GitHubStatus): GitHubStatus {
  cacheSet(statusCacheKey(), status);
  if (!status.connected) {
    cacheRemove(reposCacheKey());
    cacheRemove(countCacheKey());
  }
  return status;
}

export async function getGitHubStatus(): Promise<GitHubStatus> {
  const { data } = await apiClient.get<Envelope<GitHubStatus>>("/github/status");
  return persistStatus(data.data);
}

export async function startGitHubOAuth(): Promise<{ authorize_url: string; state: string }> {
  const { data } = await apiClient.get<Envelope<{ authorize_url: string; state: string }>>(
    "/github/oauth/start",
  );
  return data.data;
}

export async function disconnectGitHub(): Promise<void> {
  await apiClient.post("/github/disconnect");
  clearGitHubCache();
  persistStatus({ connected: false, message: "GitHub disconnected" });
}

export async function listGitHubRepos(page = 1): Promise<GitHubRepo[]> {
  const { data } = await apiClient.get<Envelope<{ items: GitHubRepo[] }>>("/github/repos", {
    params: { page, per_page: 50 },
  });
  const items = rejectDemos(data.data.items);
  if (page === 1) cacheSet(reposCacheKey(), items);
  return items;
}

export async function countGitHubRepos(): Promise<number> {
  const { data } = await apiClient.get<Envelope<{ total: number }>>("/github/repos/count");
  const total = data.data.total ?? 0;
  cacheSet(countCacheKey(), total);
  return total;
}

export async function listGitHubBranches(
  owner: string,
  repo: string,
): Promise<{ items: GitHubBranch[]; default_branch: string | null }> {
  try {
    const { data } = await apiClient.get<
      Envelope<{ items: GitHubBranch[]; default_branch: string | null }>
    >(`/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/branches`);
    cacheSet(branchesCacheKey(owner, repo), data.data);
    return data.data;
  } catch (err) {
    const cached = getCachedGitHubBranches(owner, repo);
    if (cached) return cached;
    throw err;
  }
}

export async function importRepository(payload: {
  owner: string;
  repo: string;
  branch: string;
  display_name?: string;
}): Promise<ImportResult> {
  const { data } = await apiClient.post<Envelope<ImportResult>>("/repositories/import", payload);
  return data.data;
}
