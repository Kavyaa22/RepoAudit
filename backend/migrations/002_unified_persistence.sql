-- RepoAudit 002 — unified persistence (profile → project → branch → audits/investigations)
-- Apply in Supabase SQL editor after 001_initial_schema.sql
-- Canonical copy: app/core/db/migrations/002_unified_persistence.sql

-- ------------------------------------------------------------------ projects (align with app code)
alter table public.projects
    add column if not exists private boolean not null default false,
    add column if not exists summary jsonb not null default '{}'::jsonb,
    add column if not exists latest_snapshot_id uuid,
    add column if not exists latest_commit_sha text,
    add column if not exists audit_project_id text;

alter table public.projects drop constraint if exists projects_status_check;
alter table public.projects add constraint projects_status_check
    check (status in ('importing', 'ready', 'failed', 'syncing'));

-- ----------------------------------------------------------- repo_snapshots
create table if not exists public.repo_snapshots (
    snapshot_id     uuid primary key default gen_random_uuid(),
    project_id      uuid not null
        references public.projects (project_id) on delete cascade,
    user_id         uuid references auth.users (id) on delete set null,
    branch          text not null,
    commit_sha      text not null,
    workspace_path  text not null,
    status          text not null default 'ready',
    file_count      integer not null default 0,
    line_count      integer not null default 0,
    summary         jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now(),
    constraint repo_snapshots_status_check
        check (status in ('pending', 'ready', 'failed')),
    constraint repo_snapshots_project_branch_commit_key
        unique (project_id, branch, commit_sha)
);

create index if not exists repo_snapshots_project_branch_idx
    on public.repo_snapshots (project_id, branch, created_at desc);
create index if not exists repo_snapshots_user_idx
    on public.repo_snapshots (user_id);

alter table public.projects
    drop constraint if exists projects_latest_snapshot_fk;
alter table public.projects
    add constraint projects_latest_snapshot_fk
    foreign key (latest_snapshot_id)
    references public.repo_snapshots (snapshot_id)
    on delete set null;

-- --------------------------------------------------------------- audit_runs
create table if not exists public.audit_runs (
    audit_id        uuid primary key default gen_random_uuid(),
    project_id      uuid not null
        references public.projects (project_id) on delete cascade,
    snapshot_id     uuid references public.repo_snapshots (snapshot_id) on delete set null,
    user_id         uuid references auth.users (id) on delete set null,
    branch          text not null,
    commit_sha      text,
    audit_type      text not null,
    status          text not null default 'running',
    overall_score   integer,
    is_valid        boolean,
    result          jsonb not null default '{}'::jsonb,
    error           jsonb,
    artifact_path   text,
    duration_ms     integer not null default 0,
    created_at      timestamptz not null default now(),
    finished_at     timestamptz,
    constraint audit_runs_type_check
        check (audit_type in (
            'structure', 'dead_code', 'combined', 'wiki', 'full_scan', 'pdf_export'
        )),
    constraint audit_runs_status_check
        check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled'))
);

create index if not exists audit_runs_profile_repo_idx
    on public.audit_runs (user_id, project_id, branch, created_at desc);
create index if not exists audit_runs_snapshot_idx
    on public.audit_runs (snapshot_id, created_at desc);

-- ------------------------------------------------------------- audit_findings
create table if not exists public.audit_findings (
    finding_id       uuid primary key default gen_random_uuid(),
    audit_id         uuid not null
        references public.audit_runs (audit_id) on delete cascade,
    project_id       uuid not null
        references public.projects (project_id) on delete cascade,
    snapshot_id      uuid references public.repo_snapshots (snapshot_id) on delete set null,
    user_id          uuid references auth.users (id) on delete set null,
    branch           text not null,
    finding_kind     text not null,
    severity         text,
    path             text not null default '',
    symbol_name      text not null default '',
    title            text not null default '',
    description      text not null default '',
    suggestion       text not null default '',
    confidence_score integer,
    metadata         jsonb not null default '{}'::jsonb,
    created_at       timestamptz not null default now(),
    constraint audit_findings_kind_check
        check (finding_kind in (
            'structure_violation', 'unstructured_area', 'dead_code', 'unused_dependency'
        ))
);

create index if not exists audit_findings_user_branch_idx
    on public.audit_findings (user_id, project_id, branch, created_at desc);
create index if not exists audit_findings_audit_idx
    on public.audit_findings (audit_id);

-- ------------------------------------------------ extend investigations
alter table public.investigations
    add column if not exists branch text,
    add column if not exists snapshot_id uuid
        references public.repo_snapshots (snapshot_id) on delete set null,
    add column if not exists feature_name text not null default '',
    add column if not exists action_name text not null default '',
    add column if not exists error_log text not null default '',
    add column if not exists issue_description text,
    add column if not exists result jsonb not null default '{}'::jsonb,
    add column if not exists updated_at timestamptz not null default now();

update public.investigations
set issue_description = issue
where issue_description is null and issue is not null;

create index if not exists investigations_user_branch_idx
    on public.investigations (user_id, project_id, branch, created_at desc);

-- ----------------------------------------------------- extend analysis_runs
alter table public.analysis_runs
    add column if not exists snapshot_id uuid
        references public.repo_snapshots (snapshot_id) on delete set null,
    add column if not exists branch text,
    add column if not exists commit_sha text;

-- ----------------------------------------------------- extend reports
alter table public.reports
    add column if not exists snapshot_id uuid
        references public.repo_snapshots (snapshot_id) on delete set null,
    add column if not exists branch text,
    add column if not exists audit_id uuid
        references public.audit_runs (audit_id) on delete set null;

-- ----------------------------------------------------------- updated_at triggers
drop trigger if exists investigations_touch_updated_at on public.investigations;
create trigger investigations_touch_updated_at
    before update on public.investigations
    for each row execute function public.touch_updated_at();

-- ----------------------------------------------------------- RLS
alter table public.repo_snapshots   enable row level security;
alter table public.audit_runs       enable row level security;
alter table public.audit_findings   enable row level security;

do $$
declare target text;
begin
    foreach target in array array['repo_snapshots', 'audit_runs', 'audit_findings']
    loop
        execute format('drop policy if exists %I on public.%I', target || '_owner_rw', target);
        execute format(
            'create policy %I on public.%I for all to authenticated '
            'using (user_id = auth.uid()) with check (user_id = auth.uid())',
            target || '_owner_rw', target
        );
    end loop;
end;
$$;
