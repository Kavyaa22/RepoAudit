-- RepoAudit 004 — security audit finding kinds
-- Apply in Supabase SQL editor after 003_investigation_artifacts.sql
-- Canonical copy: app/core/db/migrations/004_security_audit.sql

alter table public.audit_findings drop constraint if exists audit_findings_kind_check;
alter table public.audit_findings add constraint audit_findings_kind_check
    check (finding_kind in (
        'structure_violation',
        'unstructured_area',
        'dead_code',
        'unused_dependency',
        'secret',
        'vulnerable_dependency',
        'dangerous_pattern'
    ));
