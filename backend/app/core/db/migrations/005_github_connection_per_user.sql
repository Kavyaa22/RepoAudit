-- RepoAudit 005 — per-app-user GitHub connections
-- Apply in Supabase SQL editor after 004_security_audit.sql
-- Canonical copy: app/core/db/migrations/005_github_connection_per_user.sql
--
-- One GitHub OAuth row per app user (user_id unique). The same GitHub login
-- may be connected by more than one app account.

alter table public.github_connections
    drop constraint if exists github_connections_github_user_id_key;

drop index if exists public.github_connections_github_user_id_key;
drop index if exists public.github_connections_github_user_id_idx;
