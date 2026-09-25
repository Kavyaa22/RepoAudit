const PREFIX = "repoaudit_cache_";

/** Keep dashboard/history paintable across sessions; network refresh happens in the background. */
export const PERSISTENT_CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

type CacheEntry<T> = {
  v: T;
  t: number;
};

function getScopedKey(key: string): string {
  const activeUser =
    sessionStorage.getItem("repoaudit_active_user_id") ||
    localStorage.getItem("repoaudit_active_user_id");
  const userSegment = activeUser ? `u_${activeUser}` : "anon";
  return `${PREFIX}${userSegment}_${key}`;
}

function readEntry<T>(key: string): CacheEntry<T> | null {
  try {
    const scopedKey = getScopedKey(key);
    const raw = localStorage.getItem(scopedKey);
    if (!raw) return null;
    const entry = JSON.parse(raw) as CacheEntry<T>;
    if (!entry || typeof entry.t !== "number") return null;
    return entry;
  } catch {
    return null;
  }
}

export function cacheGet<T>(key: string, maxAgeMs = PERSISTENT_CACHE_TTL_MS): T | null {
  const entry = readEntry<T>(key);
  if (!entry) return null;
  if (Date.now() - entry.t > maxAgeMs) return null;
  return entry.v;
}

/** Return cached value even if TTL expired — used for instant first paint. */
export function cachePeek<T>(key: string): T | null {
  return readEntry<T>(key)?.v ?? null;
}

export function cacheSet<T>(key: string, value: T): void {
  try {
    const entry: CacheEntry<T> = { v: value, t: Date.now() };
    localStorage.setItem(getScopedKey(key), JSON.stringify(entry));
  } catch {
    // ignore quota / private-mode failures
  }
}

export function cacheRemove(key: string): void {
  try {
    localStorage.removeItem(getScopedKey(key));
  } catch {
    // ignore
  }
}

export function cacheRemovePrefix(prefix: string): void {
  try {
    const full = getScopedKey(prefix);
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key && key.startsWith(full)) keys.push(key);
    }
    for (const key of keys) localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export function clearAllClientCache(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key && key.startsWith(PREFIX)) keys.push(key);
    }
    for (const key of keys) localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

