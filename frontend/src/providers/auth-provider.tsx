import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiClient } from "../services/api-client";
import { TOKEN_STORAGE_KEY } from "../lib/constants";
import { env } from "../config/env";
import {
  clearUserSettings,
  setActiveUserId,
} from "../lib/user-settings";
import { clearGitHubCache } from "../services/github";
import { clearAllClientCache } from "../lib/client-cache";
import * as authService from "../services/auth";

export type AuthUser = {
  user_id: string;
  email: string;
  full_name: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    fullName: string,
    confirmPassword?: string
  ) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  updateProfile: (fullName: string) => Promise<void>;
  deleteAccount: (password: string) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

type ApiEnvelope<T> = { success: boolean; data: T };

function extractApiError(err: unknown): string | null {
  if (err instanceof Error && err.message) return err.message;
  return null;
}

function assertAuthPayload<T extends { access_token?: string }>(
  payload: T | undefined | null,
  action: "Login" | "Registration"
): asserts payload is T & { access_token: string } {
  if (payload?.access_token) return;
  throw new Error(
    `${action} failed: Invalid server response. The app may be misconfigured — ensure BACKEND_URL (or VITE_API_BASE_URL) points to the API in production.`
  );
}

function applyUserSession(
  userId: string,
  email: string,
  fullName: string,
): AuthUser {
  const u: AuthUser = { user_id: userId, email, full_name: fullName };
  setActiveUserId(userId);
  return u;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem(TOKEN_STORAGE_KEY)
  );
  const [user, setUser] = useState<AuthUser | null>(null);

  const persistToken = useCallback((next: string | null) => {
    setToken(next);
    if (next) localStorage.setItem(TOKEN_STORAGE_KEY, next);
    else localStorage.removeItem(TOKEN_STORAGE_KEY);
  }, []);

  const refreshUser = useCallback(async () => {
    if (env.authDisabled) {
      setActiveUserId(null);
      setUser(null);
      return;
    }
    if (!localStorage.getItem(TOKEN_STORAGE_KEY)) {
      setUser(null);
      setActiveUserId(null);
      return;
    }
    try {
      const me = await authService.fetchMe();
      if (me.user_id && me.email) {
        setUser(
          applyUserSession(me.user_id, me.email, me.full_name ?? me.email)
        );
      }
    } catch {
      setUser(null);
      setActiveUserId(null);
    }
  }, []);

  useEffect(() => {
    if (token && !env.authDisabled) {
      void refreshUser();
    } else if (env.authDisabled) {
      setActiveUserId(null);
    }
  }, [token, refreshUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      try {
        const res = await apiClient.post<
          ApiEnvelope<{
            user_id: string;
            email: string;
            full_name: string;
            access_token: string;
          }>
        >("/auth/login", { email, password });

        const payload = res.data?.data;
        assertAuthPayload(payload, "Login");
        persistToken(payload.access_token);
        clearGitHubCache();
        clearAllClientCache();
        setUser(
          applyUserSession(
            payload.user_id,
            payload.email,
            payload.full_name
          )
        );
      } catch (err: unknown) {
        const apiMsg = extractApiError(err);
        if (apiMsg) throw new Error(apiMsg);
        throw err;
      }
    },
    [persistToken]
  );

  const register = useCallback(
    async (
      email: string,
      password: string,
      fullName: string,
      confirmPassword?: string
    ) => {
      try {
        const res = await apiClient.post<
          ApiEnvelope<{
            user_id: string;
            email: string;
            full_name: string;
            access_token: string;
          }>
        >("/auth/register", {
          email,
          password,
          confirm_password: confirmPassword || password,
          full_name: fullName,
        });

        const payload = res.data?.data;
        assertAuthPayload(payload, "Registration");
        persistToken(payload.access_token);
        clearGitHubCache();
        clearAllClientCache();
        setUser(
          applyUserSession(
            payload.user_id,
            payload.email,
            payload.full_name
          )
        );
      } catch (err: unknown) {
        const apiMsg = extractApiError(err);
        if (apiMsg) throw new Error(apiMsg);
        throw err;
      }
    },
    [persistToken]
  );

  const logout = useCallback(async () => {
    try {
      await apiClient.post("/auth/logout");
    } catch {
      // ignore logout network errors
    } finally {
      persistToken(null);
      setUser(null);
      setActiveUserId(null);
      clearGitHubCache();
      clearAllClientCache();
    }
  }, [persistToken]);

  const updateProfile = useCallback(async (fullName: string) => {
    const me = await authService.updateMe(fullName);
    if (me.user_id && me.email) {
      setUser(applyUserSession(me.user_id, me.email, me.full_name ?? fullName));
    }
  }, []);

  const deleteAccount = useCallback(
    async (password: string) => {
      const uid = user?.user_id ?? null;
      await authService.deleteMe(password);
      if (uid) clearUserSettings(uid);
      persistToken(null);
      setUser(null);
      setActiveUserId(null);
      clearGitHubCache();
      clearAllClientCache();
    },
    [persistToken, user?.user_id]
  );

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthenticated: env.authDisabled ? true : Boolean(token),
      login,
      register,
      logout,
      refreshUser,
      updateProfile,
      deleteAccount,
    }),
    [
      user,
      token,
      login,
      register,
      logout,
      refreshUser,
      updateProfile,
      deleteAccount,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
