/**
 * Client-side audit history helpers: merge keys, tombstones, and fetch races.
 */
import { cachePeek, cacheRemove, cacheSet } from "./client-cache";
import { rejectDemos } from "./demo-filter";

/** Minimal shape shared with api.AuditHistoryRecord (avoid circular imports). */
export type HistoryRecordLike = {
  audit_id?: string;
  project_id?: string;
  id?: string;
  name: string;
  branch: string;
  created_at?: string;
  status?: string;
};

const TOMBSTONE_KEY = "audit_tombstones";
const TOMBSTONE_TTL_MS = 30 * 60 * 1000; // 30 minutes

type TombstoneMap = Record<string, number>;

let historyFetchGeneration = 0;

export function nextHistoryFetchGeneration(): number {
  historyFetchGeneration += 1;
  return historyFetchGeneration;
}

export function isHistoryFetchCurrent(generation: number): boolean {
  return generation === historyFetchGeneration;
}

function readTombstones(): TombstoneMap {
  try {
    const raw = cachePeek<TombstoneMap>(TOMBSTONE_KEY);
    if (!raw || typeof raw !== "object") return {};
    const now = Date.now();
    const fresh: TombstoneMap = {};
    for (const [id, ts] of Object.entries(raw)) {
      if (typeof ts === "number" && now - ts < TOMBSTONE_TTL_MS && id) {
        fresh[id] = ts;
      }
    }
    return fresh;
  } catch {
    return {};
  }
}

function writeTombstones(map: TombstoneMap): void {
  cacheSet(TOMBSTONE_KEY, map);
}

/** Record ids that must not reappear from stale fetches/cache until TTL expires. */
export function addAuditTombstones(ids: Array<string | null | undefined>): void {
  const map = readTombstones();
  const now = Date.now();
  for (const id of ids) {
    const key = String(id || "").trim();
    if (key) map[key] = now;
  }
  writeTombstones(map);
}

export function clearAuditTombstones(ids?: Array<string | null | undefined>): void {
  if (!ids) {
    cacheRemove(TOMBSTONE_KEY);
    return;
  }
  const map = readTombstones();
  for (const id of ids) {
    const key = String(id || "").trim();
    if (key) delete map[key];
  }
  writeTombstones(map);
}

export function getAuditTombstoneIds(): Set<string> {
  return new Set(Object.keys(readTombstones()));
}

/** Stable merge/dedupe key: prefer audit_id, else project_id+branch. */
export function auditHistoryKey(
  item: Pick<HistoryRecordLike, "audit_id" | "project_id" | "id" | "branch" | "name">,
): string {
  const auditId = String(item.audit_id || "").trim();
  if (auditId) return `audit:${auditId}`;
  const projectId = String(item.project_id || item.id || "").trim();
  const branch = String(item.branch || "main").trim().toLowerCase() || "main";
  if (projectId) return `project:${projectId}@${branch}`;
  const name = String(item.name || "").trim().toLowerCase();
  return name ? `name:${name}@${branch}` : "";
}

export function itemMatchesTombstone(
  item: Pick<HistoryRecordLike, "audit_id" | "project_id" | "id">,
  tombstones: Set<string>,
): boolean {
  if (tombstones.size === 0) return false;
  const candidates = [
    String(item.audit_id || "").trim(),
    String(item.project_id || "").trim(),
    String(item.id || "").trim(),
  ].filter(Boolean);
  return candidates.some((id) => tombstones.has(id));
}

export function filterTombstonedAudits<T extends HistoryRecordLike>(items: T[]): T[] {
  const tombstones = getAuditTombstoneIds();
  if (tombstones.size === 0) return items;
  return items.filter((item) => !itemMatchesTombstone(item, tombstones));
}

/** Clear wiki/page caches for deleted project/audit identifiers. */
export function clearWikiCachesForIds(ids: Array<string | null | undefined>): void {
  const unique = [...new Set(ids.map((id) => String(id || "").trim()).filter(Boolean))];
  if (unique.length === 0) return;

  for (const id of unique) {
    cacheRemove(`wiki:${id}`);
  }

  try {
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (!key) continue;
      const isWiki = key.includes("_wiki:") || key.includes("_wiki-page:");
      if (!isWiki) continue;
      if (unique.some((id) => key.includes(`wiki:${id}`) || key.includes(`wiki-page:${id}:`))) {
        keysToRemove.push(key);
      }
    }
    for (const key of keysToRemove) localStorage.removeItem(key);
  } catch {
    // ignore quota / private-mode failures
  }
}

export function mergeAuditHistoryRecords<T extends HistoryRecordLike>(
  dbAudits: T[],
  legacyAudits: T[],
): T[] {
  const merged = new Map<string, T>();

  // Prefer DB audits over legacy when keys collide (db applied last).
  for (const item of [...legacyAudits, ...dbAudits]) {
    const key = auditHistoryKey(item);
    if (!key) continue;
    const existing = merged.get(key);
    merged.set(
      key,
      existing
        ? ({
            ...existing,
            ...item,
            audit_id: item.audit_id || existing.audit_id,
            project_id: item.project_id || existing.project_id,
            id: item.project_id || item.id || existing.id,
          } as T)
        : item,
    );
  }

  // Collapse accidental duplicates that share project_id+branch under different keys
  const byProjectBranch = new Map<string, string>();
  for (const [key, item] of Array.from(merged.entries())) {
    const pid = String(item.project_id || item.id || "").trim();
    const branch = String(item.branch || "main").trim().toLowerCase() || "main";
    if (!pid) continue;
    const pb = `${pid}@${branch}`;
    const prevKey = byProjectBranch.get(pb);
    if (!prevKey) {
      byProjectBranch.set(pb, key);
      continue;
    }
    const prev = merged.get(prevKey);
    if (!prev) continue;
    const preferCurrent =
      Boolean(item.audit_id && !prev.audit_id) ||
      new Date(String(item.created_at || 0)).getTime() >=
        new Date(String(prev.created_at || 0)).getTime();
    if (preferCurrent) {
      merged.set(prevKey, {
        ...prev,
        ...item,
        audit_id: item.audit_id || prev.audit_id,
        project_id: item.project_id || prev.project_id,
        id: item.project_id || item.id || prev.id,
      } as T);
      if (key !== prevKey) merged.delete(key);
    } else {
      merged.delete(key);
    }
  }

  return filterTombstonedAudits(
    rejectDemos(
      Array.from(merged.values()).sort(
        (a, b) =>
          new Date(String(b.created_at || 0)).getTime() -
          new Date(String(a.created_at || 0)).getTime(),
      ),
    ) as T[],
  );
}
