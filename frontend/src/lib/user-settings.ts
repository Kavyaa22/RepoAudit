import { DEFAULT_MODEL, normalizeStoredModel } from "./model-options";

export type StructureStyle = "action_api" | "conservative";

export type UserLlmSettings = {
  openrouterApiKey: string;
  model: string;
  language: string;
  structureStyle: StructureStyle;
};

const ACTIVE_USER_KEY = "repoaudit_active_user_id";
const LEGACY_API_KEY = "repoaudit_api_key";

export const DEFAULT_LLM_SETTINGS: UserLlmSettings = {
  openrouterApiKey: "",
  model: DEFAULT_MODEL,
  language: "en",
  structureStyle: "action_api",
};

export function settingsStorageKey(userId: string | null): string {
  return `repoaudit_settings_${userId || "anonymous"}`;
}

export function setActiveUserId(userId: string | null): void {
  if (userId) {
    localStorage.setItem(ACTIVE_USER_KEY, userId);
    sessionStorage.setItem(ACTIVE_USER_KEY, userId);
  } else {
    localStorage.removeItem(ACTIVE_USER_KEY);
    sessionStorage.removeItem(ACTIVE_USER_KEY);
  }
}

export function getActiveUserId(): string | null {
  return sessionStorage.getItem(ACTIVE_USER_KEY) || localStorage.getItem(ACTIVE_USER_KEY);
}

function normalizeStructureStyle(value: unknown): StructureStyle {
  return value === "conservative" ? "conservative" : "action_api";
}

export function loadUserSettings(userId?: string | null): UserLlmSettings {
  const id = userId ?? getActiveUserId();
  const key = settingsStorageKey(id);
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<UserLlmSettings>;
      return {
        openrouterApiKey: parsed.openrouterApiKey ?? "",
        model: normalizeStoredModel(parsed.model),
        language: parsed.language || "en",
        structureStyle: normalizeStructureStyle(parsed.structureStyle),
      };
    }
  } catch {
    // fall through
  }

  const legacyKey = localStorage.getItem(LEGACY_API_KEY) ?? "";
  return { ...DEFAULT_LLM_SETTINGS, openrouterApiKey: legacyKey };
}

export function saveUserSettings(
  settings: UserLlmSettings,
  userId?: string | null,
): void {
  const id = userId ?? getActiveUserId();
  const key = settingsStorageKey(id);
  localStorage.setItem(key, JSON.stringify(settings));
  if (settings.openrouterApiKey) {
    localStorage.setItem(LEGACY_API_KEY, settings.openrouterApiKey);
  } else {
    localStorage.removeItem(LEGACY_API_KEY);
  }
}

export function clearUserSettings(userId?: string | null): void {
  const id = userId ?? getActiveUserId();
  localStorage.removeItem(settingsStorageKey(id));
}
