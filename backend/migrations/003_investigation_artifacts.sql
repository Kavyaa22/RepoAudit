-- RepoAudit 003 — investigation artifacts, retention, analytics fields
-- Apply in Supabase SQL editor after 002_unified_persistence.sql

alter table public.investigations
    add column if not exists artifact_path text not null default '',
    add column if not exists expires_at timestamptz,
    add column if not exists analytics jsonb not null default '{}'::jsonb;

update public.investigations
set expires_at = coalesce(updated_at, created_at, now()) + interval '30 days'
where expires_at is null;

create index if not exists investigations_expires_at_idx
    on public.investigations (expires_at);
