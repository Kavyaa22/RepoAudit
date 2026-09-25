-- ProjectDNA AI / RepoAudit — initial relational schema for Supabase.
--
-- Scope: mutable / relational state only. Immutable engine artifacts
-- (parser snapshots, knowledge graphs, audit reports, investigations,
-- reports) stay on disk under `{project}/.projectdna/`; the tables below
-- index them and hold state the filesystem cannot express.
--
-- Apply with the Supabase SQL editor (or `supabase db push` if using CLI).
--
-- Auth notes:
--   - Email is unique via auth.users; display names may collide.
--   - Email verification and password reset are custom (auth_tokens + your
--     SMTP). Disable Supabase built-in Auth emails in the dashboard.
--   - Backend should use the service-role key (bypasses RLS). RLS protects
--     any direct client access with the anon / authenticated keys.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------- profiles
-- App-facing user profile (display name + custom email verification state).

create table if not exists public.profiles (
    user_id             uuid primary key
        references auth.users (id) on delete cascade,
    email               text not null,
    full_name           text not null,
    email_verified_at   timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create unique index if not exists profiles_email_key
    on public.profiles (lower(email));

-- ------------------------------------------------------------- auth_tokens
-- Custom email verification and password-reset tokens (store hashes only).
-- Service-role only — no authenticated policies below.

create table if not exists public.auth_tokens (
    token_id    uuid primary key default gen_random_uuid(),
    user_id     uuid not null
        references auth.users (id) on delete cascade,
    purpose     text not null,
    token_hash  text not null,
    expires_at  timestamptz not null,
    used_at     timestamptz,
    created_at  timestamptz not null default now(),
    constraint auth_tokens_purpose_check
        check (purpose in ('email_verify', 'password_reset'))
);

create unique index if not exists auth_tokens_token_hash_key
    on public.auth_tokens (token_hash);

create index if not exists auth_tokens_user_purpose_idx
    on public.auth_tokens (user_id, purpose)
    where used_at is null;

-- ------------------------------------------------------ github_connections
-- One GitHub OAuth link per app user. Token must be encrypted at rest by
-- the backend before insert; never expose access_token_encrypted to clients.

create table if not exists public.github_connections (
    connection_id          uuid primary key default gen_random_uuid(),
    user_id                uuid not null
        references auth.users (id) on delete cascade,
    github_user_id         bigint not null,
    github_login           text not null,
    access_token_encrypted text not null,
    scopes                 text[] not null default '{}',
    token_type             text not null default 'bearer',
    connected_at           timestamptz not null default now(),
    updated_at             timestamptz not null default now(),
    last_validated_at      timestamptz
);

create unique index if not exists github_connections_user_id_key
    on public.github_connections (user_id);

-- github_user_id is NOT unique: each app user has their own GitHub link.
-- See 005_github_connection_per_user.sql for existing databases.

-- ------------------------------------------------------------ oauth_states
-- Short-lived CSRF state for GitHub OAuth. Service-role only.

create table if not exists public.oauth_states (
    state       text primary key,
    user_id     uuid not null
        references auth.users (id) on delete cascade,
    provider    text not null default 'github',
    expires_at  timestamptz not null,
    created_at  timestamptz not null default now(),
    constraint oauth_states_provider_check
        check (provider in ('github'))
);

create index if not exists oauth_states_expires_at_idx
    on public.oauth_states (expires_at);

-- ---------------------------------------------------------------- projects

create table if not exists public.projects (
    project_id         uuid primary key,
    user_id            uuid references auth.users (id) on delete cascade,
    project_name       text not null,
    display_name       text not null,
    repository_url     text not null,
    owner              text not null,
    repository_name    text not null,
    default_branch     text not null,
    workspace_path     text not null,
    status             text not null default 'importing',
    import_date        timestamptz not null default now(),
    last_sync          timestamptz,
    current_commit_sha text,
    source             text not null default 'github',
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    constraint projects_status_check
        check (status in ('importing', 'ready', 'failed', 'syncing'))
);

-- NULL user_id means "unowned" (auth disabled). COALESCE keeps uniqueness
-- meaningful in that mode, since Postgres treats NULLs as distinct.
create unique index if not exists projects_owner_repository_url_key
    on public.projects (
        coalesce(user_id, '00000000-0000-0000-0000-000000000000'::uuid),
        repository_url
    );

create unique index if not exists projects_owner_project_name_key
    on public.projects (
        coalesce(user_id, '00000000-0000-0000-0000-000000000000'::uuid),
        project_name
    );

create index if not exists projects_user_id_idx on public.projects (user_id);
create index if not exists projects_import_date_idx
    on public.projects (import_date desc);

-- ----------------------------------------------------------- analysis_runs

create table if not exists public.analysis_runs (
    run_id        uuid primary key default gen_random_uuid(),
    project_id    uuid not null
        references public.projects (project_id) on delete cascade,
    user_id       uuid references auth.users (id) on delete set null,
    kind          text not null default 'pipeline',
    stages        text[] not null default '{}',
    status        text not null default 'queued',
    current_stage text,
    progress      numeric(5, 2) not null default 0,
    attempt       integer not null default 1,
    force_rebuild boolean not null default false,
    result        jsonb not null default '{}'::jsonb,
    error         jsonb,
    created_at    timestamptz not null default now(),
    started_at    timestamptz,
    finished_at   timestamptz,
    constraint analysis_runs_status_check
        check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    constraint analysis_runs_progress_check
        check (progress >= 0 and progress <= 100)
);

create index if not exists analysis_runs_project_created_idx
    on public.analysis_runs (project_id, created_at desc);
create index if not exists analysis_runs_status_idx
    on public.analysis_runs (status);

-- ---------------------------------------------------------- investigations

create table if not exists public.investigations (
    investigation_id    text primary key,
    project_id          uuid not null
        references public.projects (project_id) on delete cascade,
    user_id             uuid references auth.users (id) on delete set null,
    run_id              uuid references public.analysis_runs (run_id) on delete set null,
    issue               text not null,
    knowledge_id        text,
    snapshot_id         text,
    commit_sha          text,
    status              text not null default 'complete',
    root_cause          text,
    confidence          numeric(4, 3),
    ai_available        boolean not null default false,
    affected_files      integer not null default 0,
    correlated_findings integer not null default 0,
    path                text not null,
    duration_ms         integer not null default 0,
    created_at          timestamptz not null default now(),
    constraint investigations_status_check
        check (status in ('complete', 'incomplete', 'failed', 'corrupted')),
    constraint investigations_confidence_check
        check (confidence is null or (confidence >= 0 and confidence <= 1))
);

create index if not exists investigations_project_created_idx
    on public.investigations (project_id, created_at desc);

-- ----------------------------------------------------------- chat_sessions

create table if not exists public.chat_sessions (
    session_id    uuid primary key default gen_random_uuid(),
    project_id    uuid not null
        references public.projects (project_id) on delete cascade,
    user_id       uuid references auth.users (id) on delete set null,
    title         text not null default 'New chat',
    knowledge_id  text,
    message_count integer not null default 0,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists chat_sessions_project_updated_idx
    on public.chat_sessions (project_id, updated_at desc);

-- ----------------------------------------------------------- chat_messages

create table if not exists public.chat_messages (
    message_id        uuid primary key default gen_random_uuid(),
    session_id        uuid not null
        references public.chat_sessions (session_id) on delete cascade,
    project_id        uuid not null
        references public.projects (project_id) on delete cascade,
    user_id           uuid references auth.users (id) on delete set null,
    role              text not null,
    content           text not null default '',
    citations         jsonb not null default '[]'::jsonb,
    context           jsonb not null default '{}'::jsonb,
    knowledge_id      text,
    model             text,
    prompt_tokens     integer not null default 0,
    completion_tokens integer not null default 0,
    ai_available      boolean not null default false,
    latency_ms        integer,
    created_at        timestamptz not null default now(),
    constraint chat_messages_role_check
        check (role in ('user', 'assistant', 'system'))
);

create index if not exists chat_messages_session_created_idx
    on public.chat_messages (session_id, created_at asc);

-- ----------------------------------------------------------------- reports

create table if not exists public.reports (
    report_id            text primary key,
    project_id           uuid not null
        references public.projects (project_id) on delete cascade,
    user_id              uuid references auth.users (id) on delete set null,
    report_type          text not null,
    formats              text[] not null default '{}',
    title                text,
    knowledge_id         text,
    audit_id             text,
    investigation_id     text,
    status               text not null default 'complete',
    include_ai_narrative boolean not null default false,
    ai_available         boolean not null default false,
    path                 text not null,
    duration_ms          integer not null default 0,
    created_at           timestamptz not null default now(),
    constraint reports_status_check
        check (status in ('complete', 'incomplete', 'failed', 'corrupted'))
);

create index if not exists reports_project_created_idx
    on public.reports (project_id, created_at desc);
create index if not exists reports_type_idx on public.reports (report_type);

-- ---------------------------------------------------------------- ai_usage

create table if not exists public.ai_usage (
    usage_id          uuid primary key default gen_random_uuid(),
    project_id        uuid references public.projects (project_id) on delete set null,
    user_id           uuid references auth.users (id) on delete set null,
    feature           text not null,
    provider          text not null default 'openrouter',
    model             text not null,
    prompt_tokens     integer not null default 0,
    completion_tokens integer not null default 0,
    total_tokens      integer not null default 0,
    cost_usd          numeric(12, 6),
    latency_ms        integer,
    success           boolean not null default true,
    error_code        text,
    request_id        text,
    created_at        timestamptz not null default now()
);

create index if not exists ai_usage_created_idx on public.ai_usage (created_at desc);
create index if not exists ai_usage_project_idx on public.ai_usage (project_id);
create index if not exists ai_usage_feature_idx on public.ai_usage (feature);

-- ------------------------------------------------------------ updated_at

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at
    before update on public.profiles
    for each row execute function public.touch_updated_at();

drop trigger if exists github_connections_touch_updated_at on public.github_connections;
create trigger github_connections_touch_updated_at
    before update on public.github_connections
    for each row execute function public.touch_updated_at();

drop trigger if exists projects_touch_updated_at on public.projects;
create trigger projects_touch_updated_at
    before update on public.projects
    for each row execute function public.touch_updated_at();

drop trigger if exists chat_sessions_touch_updated_at on public.chat_sessions;
create trigger chat_sessions_touch_updated_at
    before update on public.chat_sessions
    for each row execute function public.touch_updated_at();

-- Auto-create a profile row when a user signs up (Auth Admin / signup API).
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (user_id, email, full_name)
    values (
        new.id,
        coalesce(new.email, ''),
        coalesce(
            new.raw_user_meta_data ->> 'full_name',
            new.raw_user_meta_data ->> 'name',
            split_part(coalesce(new.email, 'user'), '@', 1)
        )
    )
    on conflict (user_id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ----------------------------------------------------------------- RLS
-- The backend uses the service-role key, which bypasses RLS. These policies
-- protect any direct client access with the anon / authenticated keys.
-- auth_tokens and oauth_states have no authenticated policies (service-role only).

alter table public.profiles            enable row level security;
alter table public.auth_tokens         enable row level security;
alter table public.github_connections  enable row level security;
alter table public.oauth_states        enable row level security;
alter table public.projects            enable row level security;
alter table public.analysis_runs       enable row level security;
alter table public.investigations      enable row level security;
alter table public.chat_sessions       enable row level security;
alter table public.chat_messages       enable row level security;
alter table public.reports             enable row level security;
alter table public.ai_usage            enable row level security;

do $$
declare
    target text;
begin
    foreach target in array array[
        'profiles', 'github_connections',
        'projects', 'analysis_runs', 'investigations',
        'chat_sessions', 'chat_messages', 'reports', 'ai_usage'
    ]
    loop
        execute format(
            'drop policy if exists %I on public.%I',
            target || '_owner_rw', target
        );
        execute format(
            'create policy %I on public.%I for all to authenticated '
            'using (user_id = auth.uid()) with check (user_id = auth.uid())',
            target || '_owner_rw', target
        );
    end loop;
end;
$$;

-- Safe client view of GitHub connection metadata (no encrypted token).
create or replace view public.github_connections_public
with (security_invoker = true)
as
select
    connection_id,
    user_id,
    github_user_id,
    github_login,
    scopes,
    token_type,
    connected_at,
    updated_at,
    last_validated_at
from public.github_connections;
