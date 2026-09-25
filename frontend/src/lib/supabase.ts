/**
 * Supabase anon client — config only.
 * Auth UI lives in providers/auth-provider; do not put login forms here.
 */

import { env } from "../config/env";

export type SupabaseClientLike = {
  url: string;
  anonKey: string;
  configured: boolean;
};

export function getSupabaseConfig(): SupabaseClientLike {
  return {
    url: env.supabaseUrl,
    anonKey: env.supabaseAnonKey,
    configured: Boolean(env.supabaseUrl && env.supabaseAnonKey),
  };
}
