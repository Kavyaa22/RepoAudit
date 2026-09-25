import { loadUserSettings } from "./user-settings";
import { TOKEN_STORAGE_KEY } from "./constants";
import { cacheGet, cachePeek, cacheRemove, cacheSet } from "./client-cache";
import { rejectDemos } from "./demo-filter";
import {
  addAuditTombstones,
  clearWikiCachesForIds,
  filterTombstonedAudits,
  mergeAuditHistoryRecords,
  nextHistoryFetchGeneration,
  isHistoryFetchCurrent,
} from "./audit-history";

export const API_BASE = "/api";
const BASE = API_BASE;

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const settings = loadUserSettings();
  if (settings.openrouterApiKey) {
    headers["x-api-key"] = settings.openrouterApiKey;
  }
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function getChatHeaders(): Record<string, string> {
  const headers = getHeaders();
  const settings = loadUserSettings();
  if (settings.model) headers["x-model"] = settings.model;
  if (settings.language) headers["x-language"] = settings.language;
  return headers;
}

export interface ScanRequest {
  path?: string;
  url?: string;
  language?: string;
  model?: string;
  display_name?: string;
  branch?: string;
  owner?: string;
  repository_name?: string;
  project_id?: string;
  /** action_api (default) or conservative */
  structure_style?: string;
}

export interface ProjectInfo {
  id: string;
  name: string;
  status: string;
  total_files: number;
  total_lines: number;
  error?: string;
  branch?: string;
}

export interface WikiStructure {
  project_name: string;
  sidebar: SidebarItem[];
  pages: PageMeta[];
  structure_audit?: any;
  dead_code_audit?: any;
  security_audit?: any;
}

export interface SidebarItem {
  title: string;
  page_id: string;
  children?: SidebarItem[];
}

export interface PageMeta {
  id: string;
  title: string;
  order: number;
  parent_id: string;
}

export interface WikiPage {
  id: string;
  title: string;
  content: string;
}

export interface DeadCodeFinding {
  index: number;
  path: string;
  symbol_name: string;
  category: string;
  confidence_level: "HIGH" | "MEDIUM" | "LOW";
  confidence_score: number;
  signals_found: string[];
  description: string;
  suggestion: string;
}

export interface DeadCodeAuditData {
  project_name: string;
  branch: string;
  total_findings: number;
  health_score: number;
  summary_verdict: string;
  findings: DeadCodeFinding[];
  counts_by_category: Record<string, number>;
  error?: string;
}

export interface DeadCodePromptRequest {
  finding_index?: number;
  finding_indices?: number[];
  confidence?: "HIGH" | "MEDIUM";
  category?: string;
}

export interface DeadCodePromptResponse {
  prompt: string;
  count: number;
  finding_indices: number[];
}

export interface AuditHistoryRecord {
  audit_id?: string;
  project_id?: string;
  id?: string;
  name: string;
  display_name?: string;
  status: string;
  error?: string;
  total_files: number;
  total_lines: number;
  created_at: string;
  score: number;
  is_valid: boolean;
  branch: string;
  structure_audit?: any;
  dead_code_audit?: any;
  security_audit?: any;
  wiki_summary?: any;
  owner?: string | null;
  repository_name?: string | null;
  repository_url?: string | null;
}

export function getCachedAudits(): AuditHistoryRecord[] {
  return filterTombstonedAudits(rejectDemos(cachePeek<AuditHistoryRecord[]>("audits") ?? []));
}

export function getCachedLegacyScans(): AuditHistoryRecord[] {
  return filterTombstonedAudits(rejectDemos(cachePeek<AuditHistoryRecord[]>("legacy_scans") ?? []));
}

function mapAuditRecord(item: Record<string, unknown>): AuditHistoryRecord {
  return {
    audit_id: String(item.audit_id ?? ""),
    project_id: String(item.project_id ?? item.id ?? ""),
    id: String(item.project_id ?? item.id ?? item.audit_id ?? ""),
    name: String(item.name ?? item.display_name ?? "Repository"),
    display_name: item.display_name as string | undefined,
    status: item.status === "succeeded" || item.status === "done" ? "done" : String(item.status ?? "done"),
    total_files: Number(item.total_files ?? 0),
    total_lines: Number(item.total_lines ?? 0),
    created_at: String(item.created_at ?? ""),
    score: Number(item.overall_score ?? item.score ?? 100),
    is_valid: item.is_valid !== false,
    branch: String(item.branch ?? "main"),
    structure_audit: item.structure_audit,
    dead_code_audit: item.dead_code_audit,
    security_audit: item.security_audit,
    wiki_summary: item.wiki_summary,
    owner: (item.owner as string | undefined) ?? null,
    repository_name: (item.repository_name as string | undefined) ?? null,
    repository_url: (item.repository_url as string | undefined) ?? null,
  };
}

export async function listAudits(opts?: { allowCacheFallback?: boolean }): Promise<AuditHistoryRecord[]> {
  const allowCacheFallback = opts?.allowCacheFallback !== false;
  try {
    const res = await fetch(`${API_BASE}/v1/audits`, { headers: getHeaders() });
    if (!res.ok) {
      if (allowCacheFallback) return getCachedAudits();
      throw new Error(`Failed to list audits (${res.status})`);
    }
    const body = await res.json();
    const items = body?.data?.items ?? [];
    const mapped = filterTombstonedAudits(
      rejectDemos((items as Record<string, unknown>[]).map((item) => mapAuditRecord(item))),
    );
    cacheSet("audits", mapped);
    return mapped;
  } catch (err) {
    if (allowCacheFallback) return getCachedAudits();
    throw err;
  }
}

/**
 * In-flight / legacy scans. Prefer /v1/audits for completed history;
 * use this mainly to surface scanning/error rows not yet in audit_runs.
 */
export async function listLegacyScans(opts?: { allowCacheFallback?: boolean }): Promise<AuditHistoryRecord[]> {
  const allowCacheFallback = opts?.allowCacheFallback !== false;
  try {
    const res = await fetch(`${API_BASE}/scans`, { headers: getHeaders() });
    if (!res.ok) {
      if (allowCacheFallback) return getCachedLegacyScans();
      throw new Error(`Failed to list scans (${res.status})`);
    }
    const body = await res.json();
    const items = Array.isArray(body) ? body : [];
    const mapped = filterTombstonedAudits(
      rejectDemos(items.map((item: Record<string, unknown>) => mapAuditRecord(item))),
    );
    cacheSet("legacy_scans", mapped);
    return mapped;
  } catch (err) {
    if (allowCacheFallback) return getCachedLegacyScans();
    throw err;
  }
}

export function mergeAuditHistory(
  dbAudits: AuditHistoryRecord[],
  legacyAudits: AuditHistoryRecord[],
): AuditHistoryRecord[] {
  return mergeAuditHistoryRecords(dbAudits, legacyAudits);
}

export function getCachedAuditHistory(): AuditHistoryRecord[] {
  const cached = cachePeek<AuditHistoryRecord[]>("audit_history");
  if (cached) return filterTombstonedAudits(rejectDemos(cached));
  return mergeAuditHistory(getCachedAudits(), getCachedLegacyScans());
}

export type DeleteAuditResult = {
  deleted_ids: string[];
  purged_project_ids: string[];
};

export async function deleteAudit(
  ...identifiers: Array<string | null | undefined>
): Promise<DeleteAuditResult> {
  const unique = [...new Set(identifiers.map((id) => String(id || "").trim()).filter(Boolean))];
  if (unique.length === 0) {
    throw new Error("Audit identifier is required");
  }

  let lastMessage = "Failed to delete audit";
  let result: DeleteAuditResult | null = null;

  for (const identifier of unique) {
    try {
      const res = await fetch(`${API_BASE}/v1/audits/${encodeURIComponent(identifier)}`, {
        method: "DELETE",
        headers: getHeaders(),
      });
      const body = await res.json().catch(() => null);
      if (res.ok) {
        const data = body?.data ?? body ?? {};
        result = {
          deleted_ids: Array.isArray(data.deleted_ids)
            ? data.deleted_ids.map(String)
            : [identifier],
          purged_project_ids: Array.isArray(data.purged_project_ids)
            ? data.purged_project_ids.map(String)
            : [],
        };
        break;
      }
      const detail = body?.detail;
      if (detail && typeof detail === "object" && "message" in detail) {
        lastMessage = String(detail.message);
      } else if (typeof detail === "string") {
        lastMessage = detail;
      } else if (body?.error?.message) {
        lastMessage = String(body.error.message);
      } else {
        lastMessage = `Failed to delete audit (${res.status})`;
      }
    } catch (networkErr) {
      lastMessage = networkErr instanceof Error ? networkErr.message : "Network error during audit deletion";
    }
  }

  if (!result) {
    throw new Error(lastMessage);
  }

  const allIds = [...result.deleted_ids, ...result.purged_project_ids, ...unique];
  addAuditTombstones(allIds);
  clearWikiCachesForIds(allIds);
  // Invalidate list caches only after confirmed success
  cacheRemove("audits");
  cacheRemove("legacy_scans");
  cacheRemove("audit_history");
  // Bump generation so in-flight history fetches are ignored
  nextHistoryFetchGeneration();

  return result;
}

/** Fetch and merge history with race protection. Returns null if superseded. */
export async function fetchMergedAuditHistory(opts?: {
  allowCacheFallback?: boolean;
}): Promise<AuditHistoryRecord[] | null> {
  const generation = nextHistoryFetchGeneration();
  const allowCacheFallback = opts?.allowCacheFallback !== false;
  try {
    const [dbAudits, legacyAudits] = await Promise.all([
      listAudits({ allowCacheFallback }).catch(() =>
        allowCacheFallback ? getCachedAudits() : ([] as AuditHistoryRecord[]),
      ),
      listLegacyScans({ allowCacheFallback }).catch(() =>
        allowCacheFallback ? getCachedLegacyScans() : ([] as AuditHistoryRecord[]),
      ),
    ]);
    if (!isHistoryFetchCurrent(generation)) return null;
    const merged = mergeAuditHistory(dbAudits, legacyAudits);
    cacheSet("audit_history", merged);
    return merged;
  } catch {
    if (!isHistoryFetchCurrent(generation)) return null;
    if (allowCacheFallback) return getCachedAuditHistory();
    throw new Error("Failed to load audit history");
  }
}

/** Count distinct repositories that have at least one completed audit. */
export async function countAuditedRepos(): Promise<number> {
  const merged = (await fetchMergedAuditHistory()) ?? getCachedAuditHistory();

  const keys = new Set<string>();
  for (const item of merged) {
    const status = String(item.status ?? "");
    if (status !== "done" && status !== "succeeded") continue;
    const key = String(item.project_id || item.id || item.audit_id || item.name || "");
    if (key) keys.add(key);
  }
  return keys.size;
}

export async function scanProject(req: ScanRequest): Promise<ProjectInfo> {
  const settings = loadUserSettings();
  const payload: ScanRequest = {
    ...req,
    model: req.model ?? settings.model,
    language: req.language ?? settings.language,
    structure_style: req.structure_style ?? settings.structureStyle,
  };
  const res = await fetch(`${BASE}/scan`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(payload),
  });
  return res.json();
}

export interface ScanProgressSnapshot {
  id: string;
  name?: string;
  status: string;
  progress: string[];
  error?: string;
}

export async function getScanProgress(projectId: string): Promise<ScanProgressSnapshot> {
  const res = await fetch(`${BASE}/project/${encodeURIComponent(projectId)}/progress`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to load scan progress (${res.status})`);
  }
  const data = await res.json();
  return {
    id: String(data?.id ?? projectId),
    name: data?.name ? String(data.name) : undefined,
    status: String(data?.status ?? "scanning"),
    progress: Array.isArray(data?.progress) ? data.progress.map((step: unknown) => String(step)) : [],
    error: data?.error ? String(data.error) : "",
  };
}

export function streamScanProgress(
  projectId: string,
  onProgress: (step: string) => void,
  onDone: (status: string, error?: string) => void,
) {
  let stopped = false;
  let seen = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let inFlight = false;
  let notFoundTries = 0;
  const pollMs = 2500;
  const maxNotFound = 8;

  const stop = () => {
    stopped = true;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const schedule = () => {
    if (stopped) return;
    timer = setTimeout(() => {
      void tick();
    }, pollMs);
  };

  const tick = async () => {
    if (stopped || inFlight) return;
    inFlight = true;
    try {
      const data = await getScanProgress(projectId);
      if (stopped) return;

      const missing =
        data.status === "error" &&
        data.error === "Project not found" &&
        data.progress.length === 0;
      if (missing) {
        notFoundTries += 1;
        if (notFoundTries >= maxNotFound) {
          stop();
          onDone("error", "Scan status could not be loaded. Refresh the page.");
          return;
        }
        schedule();
        return;
      }
      notFoundTries = 0;

      while (seen < data.progress.length) {
        onProgress(data.progress[seen]);
        seen += 1;
      }

      if (data.status === "done" || data.status === "error") {
        stop();
        onDone(data.status, data.error || undefined);
        return;
      }
    } catch {
      // Keep polling through proxy/HTTP2 drops. Never treat a network blip as scan failure.
    } finally {
      inFlight = false;
    }
    schedule();
  };

  void tick();
  return { close: stop };
}

export async function getWiki(projectId: string): Promise<WikiStructure> {
  const cacheKey = `wiki:${projectId}`;
  try {
    const res = await fetch(`${BASE}/project/${projectId}/wiki`, { headers: getHeaders() });
    const data = await res.json();
    if (data && !("error" in data)) {
      cacheSet(cacheKey, data);
      return data;
    }
    // Drop stale wiki cache when the server says the project is gone / not ready
    cacheRemove(cacheKey);
    return data;
  } catch (err) {
    const cached = cacheGet<WikiStructure>(cacheKey);
    if (cached) return cached;
    throw err;
  }
}

export async function getPage(projectId: string, pageId: string): Promise<WikiPage> {
  const cacheKey = `wiki-page:${projectId}:${pageId}`;
  try {
    const res = await fetch(`${BASE}/project/${projectId}/wiki/${encodeURIComponent(pageId)}`, { headers: getHeaders() });
    const data = await res.json();
    if (data && !("error" in data)) cacheSet(cacheKey, data);
    return data;
  } catch (err) {
    const cached = cacheGet<WikiPage>(cacheKey);
    if (cached) return cached;
    throw err;
  }
}

export async function getFileContent(projectId: string, filePath: string) {
  const res = await fetch(`${BASE}/project/${projectId}/file/${filePath}`, { headers: getHeaders() });
  return res.json();
}

export async function getDeadCodeAudit(projectId: string): Promise<DeadCodeAuditData> {
  const res = await fetch(`${BASE}/project/${projectId}/dead-code-audit`, { headers: getHeaders() });
  return res.json();
}

export async function generateDeadCodePrompt(
  projectId: string,
  req: DeadCodePromptRequest,
): Promise<DeadCodePromptResponse> {
  const res = await fetch(`${BASE}/project/${projectId}/dead-code/prompt`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`Failed to generate prompt: ${res.statusText}`);
  }
  return res.json();
}

/*
 * AI chat disabled — Issue Investigator is the primary workflow.
 * Original streamChat implementation preserved below for reference.
 *
export function streamChat(
  projectId: string,
  question: string,
  onChunk: (data: Record<string, unknown>) => void,
  onDone: () => void,
  onError?: (message: string) => void,
) {
  const parseSseLine = (line: string) => {
    if (!line.startsWith("data: ")) return;
    try {
      const data = JSON.parse(line.slice(6)) as Record<string, unknown>;
      onChunk(data);
      if (data.error && typeof data.error === "string") {
        onError?.(data.error);
      }
    } catch {
      // ignore malformed SSE lines
    }
  };

  fetch(`${BASE}/project/${projectId}/chat`, {
    method: "POST",
    headers: getChatHeaders(),
    body: JSON.stringify({ question }),
  })
    .then(async (res) => {
      const contentType = res.headers.get("content-type") || "";

      if (!res.ok) {
        const text = await res.text().catch(() => "");
        onError?.(text || `Chat failed (${res.status})`);
        onDone();
        return;
      }

      if (contentType.includes("application/json")) {
        try {
          const data = (await res.json()) as { error?: string };
          onError?.(data.error || "Chat request failed.");
        } catch {
          onError?.("Chat request failed.");
        }
        onDone();
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        onError?.("Browser could not read the chat response stream.");
        onDone();
        return;
      }

      let buffer = "";
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        onDone();
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          parseSseLine(line);
        }
      }
      buffer += decoder.decode();
      for (const line of buffer.split("\n")) {
        parseSseLine(line);
      }
      finish();
    })
    .catch((err: unknown) => {
      onError?.(err instanceof Error ? err.message : String(err));
      onDone();
    });
}
*/
