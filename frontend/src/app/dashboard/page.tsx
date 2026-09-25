import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getHealth, getCachedHealth, type HealthResponse } from "../../services/health";
import {
  countGitHubRepos,
  disconnectGitHub,
  getCachedGitHubRepoCount,
  getCachedGitHubStatus,
  getGitHubStatus,
  startGitHubOAuth,
  type GitHubStatus,
} from "../../services/github";
import { listProjects, getCachedProjects, type ProjectSummary } from "../../services/projects";
import {
  fetchMergedAuditHistory,
  getCachedAuditHistory,
  type AuditHistoryRecord,
} from "../../lib/api";
import { cacheSet } from "../../lib/client-cache";
import { rejectDemos } from "../../lib/demo-filter";

function apiErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "response" in err) {
    const response = (err as { response?: { data?: { error?: { message?: string }; detail?: unknown } } })
      .response;
    const detail = response?.data?.detail;
    if (detail && typeof detail === "object" && detail !== null && "message" in detail) {
      return String((detail as { message: string }).message);
    }
    if (typeof detail === "string") return detail;
    if (response?.data?.error?.message) return response.data.error.message;
  }
  return err instanceof Error ? err.message : "Something went wrong";
}

export default function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState<GitHubStatus | null>(() => getCachedGitHubStatus());
  const [projects, setProjects] = useState<ProjectSummary[]>(() => getCachedProjects());
  const [auditedRepoCount, setAuditedRepoCount] = useState(() => {
    const keys = new Set(
      getCachedAuditHistory()
        .filter((a) => a.status === "done" || a.status === "succeeded")
        .map((a) => a.project_id || a.id || a.audit_id || a.name),
    );
    return keys.size;
  });
  const [githubRepoCount, setGithubRepoCount] = useState<number | null>(() => getCachedGitHubRepoCount());
  const [health, setHealth] = useState<HealthResponse | null>(() => getCachedHealth());
  const [auditsList, setAuditsList] = useState<AuditHistoryRecord[]>(() => getCachedAuditHistory());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [loadingKpis, setLoadingKpis] = useState(
    () => !getCachedGitHubStatus() && getCachedAuditHistory().length === 0 && !getCachedHealth(),
  );

  const refresh = useCallback(async (opts?: { silent?: boolean }) => {
    setError(null);
    const hasCache = Boolean(getCachedGitHubStatus() || getCachedAuditHistory().length || getCachedHealth());
    if (!opts?.silent && !hasCache) setLoadingKpis(true);
    try {
      const [ghResult, projResult, healthResult, auditsFetchResult] = await Promise.allSettled([
        getGitHubStatus(),
        listProjects(),
        getHealth(),
        fetchMergedAuditHistory(),
      ]);

      if (ghResult.status === "fulfilled") {
        setStatus(ghResult.value);
        if (ghResult.value.connected) {
          void countGitHubRepos()
            .then((total) => setGithubRepoCount(total))
            .catch(() => {
              const cached = getCachedGitHubRepoCount();
              if (cached != null) setGithubRepoCount(cached);
            });
        } else {
          setGithubRepoCount(null);
        }
      } else {
        setStatus({ connected: false });
        setGithubRepoCount(null);
      }

      if (projResult.status === "fulfilled") {
        setProjects(rejectDemos(projResult.value));
      }

      const merged =
        auditsFetchResult.status === "fulfilled" && auditsFetchResult.value != null
          ? auditsFetchResult.value
          : getCachedAuditHistory();
      cacheSet("audit_history", merged);
      setAuditsList(merged);

      const auditedKeys = new Set(
        merged
          .filter((a) => a.status === "done" || a.status === "succeeded")
          .map((a) => String(a.project_id || a.id || a.audit_id || a.name || "")),
      );
      setAuditedRepoCount(auditedKeys.size);

      if (healthResult.status === "fulfilled") {
        setHealth(healthResult.value);
      }

      const failures = [ghResult, projResult, healthResult, auditsFetchResult].filter(
        (r) => r.status === "rejected",
      );
      if (failures.length > 0 && failures.length === 4) {
        setError(apiErrorMessage((failures[0] as PromiseRejectedResult).reason));
      }
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoadingKpis(false);
    }
  }, []);

  useEffect(() => {
    const github = searchParams.get("github");
    const reason = searchParams.get("reason");
    if (github === "connected") {
      setBanner("GitHub connected successfully.");
      setSearchParams({}, { replace: true });
      void refresh();
    } else if (github === "error") {
      setBanner(`GitHub connection failed${reason ? `: ${reason}` : ""}.`);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams, refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void refresh({ silent: true });
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    const poll = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refresh({ silent: true });
      }
    }, 15000);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(poll);
    };
  }, [refresh]);

  async function onConnect() {
    setBusy(true);
    setError(null);
    try {
      const { authorize_url } = await startGitHubOAuth();
      window.location.href = authorize_url;
    } catch (err) {
      setError(apiErrorMessage(err));
      setBusy(false);
    }
  }

  async function onDisconnect() {
    setBusy(true);
    setError(null);
    try {
      await disconnectGitHub();
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const totalRepos = githubRepoCount ?? 0;
  const auditedRepos = Math.max(
    auditedRepoCount,
    auditsList.filter((a) => a.status === "done" || a.status === "succeeded").length,
    projects.filter((p) => Boolean(p.audit_project_id)).length
  );

  const isHealthy = health?.status === "ok" || health?.status === "healthy";
  const isConnected = Boolean(status?.connected);

  // Dynamic calculation of Issue Summary & Security Score from real audits
  const issueStats = useMemo(() => {
    let critical = 0;
    let high = 0;
    let medium = 0;
    let low = 0;
    let scoreSum = 0;
    let scoreCount = 0;

    for (const item of auditsList) {
      if (typeof item.score === "number" && item.score > 0) {
        scoreSum += item.score;
        scoreCount++;
      }

      if (item.security_audit?.findings && Array.isArray(item.security_audit.findings)) {
        for (const f of item.security_audit.findings) {
          const sev = String(f.severity || "").toLowerCase();
          if (sev === "critical") critical++;
          else if (sev === "high") high++;
          else if (sev === "medium") medium++;
          else low++;
        }
      }

      if (item.dead_code_audit?.findings && Array.isArray(item.dead_code_audit.findings)) {
        for (const f of item.dead_code_audit.findings) {
          if (f.confidence_level === "HIGH") high++;
          else if (f.confidence_level === "MEDIUM") medium++;
          else low++;
        }
      } else if (item.dead_code_audit?.total_findings) {
        medium += Number(item.dead_code_audit.total_findings);
      }

      if (item.structure_audit) {
        if (item.structure_audit.critical_issues) {
          critical += Number(item.structure_audit.critical_issues);
        }
        if (item.structure_audit.warnings) {
          medium += Number(item.structure_audit.warnings);
        }
      }
    }

    const totalCalculated = critical + high + medium + low;
    
    return {
      critical,
      high,
      medium,
      low,
      total: totalCalculated,
    };
  }, [auditsList]);

  // Donut SVG Math calculations
  const { critical, high, medium, low, total } = issueStats;
  const pCritical = total > 0 ? (critical / total) * 100 : 0;
  const pHigh = total > 0 ? (high / total) * 100 : 0;
  const pMedium = total > 0 ? (medium / total) * 100 : 0;
  const pLow = total > 0 ? (low / total) * 100 : 0;

  const offsetCritical = 0;
  const offsetHigh = -pCritical;
  const offsetMedium = -(pCritical + pHigh);
  const offsetLow = -(pCritical + pHigh + pMedium);

  // Dynamic Recent Audit Activity items
  const recentActivityList = useMemo(() => {
    if (auditsList.length > 0) {
      return auditsList.slice(0, 4).map((item) => ({
        id: item.id || item.audit_id || item.name,
        name: item.name || item.display_name || "Repository",
        type: "Security & Quality Audit",
        status: item.status === "done" || item.status === "succeeded" ? "Completed" : item.status === "scanning" ? "In Progress" : "Failed",
        time: item.created_at ? new Date(item.created_at).toLocaleDateString() : "Recently",
      }));
    }
    return [];
  }, [auditsList]);

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-8 pt-0">
      {/* Dashboard Top Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight mt-0 pt-0">Dashboard</h1>
        <p className="text-xs text-slate-500 font-medium mt-0.5">
          Overview of repository audits, security, and integrations.
        </p>
      </div>

      {banner && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-800 flex items-center justify-between">
          <span>{banner}</span>
          <button onClick={() => setBanner(null)} className="text-emerald-600 font-semibold hover:underline">Dismiss</button>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-700">
          {error}
        </div>
      )}

      {/* 4 KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Backend Engine */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-[#F0F5FF] text-[#3B82F6] flex items-center justify-center shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
            </svg>
          </div>
          <div>
            <span className="text-[13px] font-medium text-slate-400 block">Backend Engine</span>
            <div className="text-base font-bold text-slate-900 inline-flex items-center gap-1.5 mt-0.5">
              <span>{loadingKpis ? "…" : isHealthy ? "Healthy" : "Offline"}</span>
              <span className={`w-2 h-2 rounded-full ${isHealthy ? "bg-emerald-500" : "bg-slate-300"}`}></span>
            </div>
            <p className="text-[12px] text-slate-400 mt-0.5">FastAPI backend health</p>
          </div>
        </div>

        {/* Card 2: GitHub Connection */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-[#ECFDF5] text-[#10B981] flex items-center justify-center shrink-0">
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
          </div>
          <div>
            <span className="text-[13px] font-medium text-slate-400 block">GitHub Connection</span>
            <div className="text-base font-bold text-slate-900 inline-flex items-center gap-1.5 mt-0.5">
              <span>{loadingKpis ? "…" : isConnected ? "Connected" : "Disconnected"}</span>
              <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-emerald-500" : "bg-slate-300"}`}></span>
            </div>
            <p className="text-[12px] text-slate-400 mt-0.5">OAuth status</p>
          </div>
        </div>

        {/* Card 3: Accessible Repos */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-[#F5F3FF] text-[#8B5CF6] flex items-center justify-center shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
          </div>
          <div>
            <span className="text-[13px] font-medium text-slate-400 block">Accessible Repos</span>
            <div className="text-xl font-bold text-slate-900 mt-0.5">
              {loadingKpis ? "…" : totalRepos}
            </div>
            <p className="text-[12px] text-slate-400 mt-0.5">Public & private repos</p>
          </div>
        </div>

        {/* Card 4: Audited Projects */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-[#FFF7ED] text-[#F97316] flex items-center justify-center shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <span className="text-[13px] font-medium text-slate-400 block">Audited Projects</span>
            <div className="text-xl font-bold text-slate-900 mt-0.5">
              {loadingKpis ? "…" : auditedRepos}
            </div>
            <p className="text-[12px] text-slate-400 mt-0.5">Completed audit reports</p>
          </div>
        </div>
      </div>

      {/* Main GitHub Connection Section */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs flex flex-col md:flex-row items-center justify-between gap-6">
        {/* Left Illustration Graphic Box */}
        <div className="flex items-center gap-5 w-full md:w-auto">
          <div className="w-36 h-24 rounded-2xl bg-[#EFF5FF] border border-[#DBEAFE] flex items-center justify-center relative shrink-0">
            <div className="w-20 h-14 bg-white rounded-xl shadow-xs border border-slate-100 flex items-center justify-center">
              <svg className="w-8 h-8 text-slate-800" fill="currentColor" viewBox="0 0 24 24">
                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
            </div>
            <div className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-emerald-500 border-2 border-white text-white flex items-center justify-center shadow-2xs">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
              </svg>
            </div>
          </div>

          <div>
            <h2 className="text-lg font-bold text-slate-900">GitHub Connection</h2>
            <p className="text-xs text-slate-500 max-w-md mt-1 leading-relaxed">
              Connect your GitHub account to import repositories, analyze code and run security audits.
            </p>
          </div>
        </div>

        {/* Right Action Buttons */}
        <div className="flex flex-col items-stretch md:items-end gap-2.5 w-full md:w-auto">
          {status?.connected ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onDisconnect()}
              className="px-5 py-2.5 bg-[#3B82F6] hover:bg-[#2563EB] text-white rounded-xl text-xs font-bold transition-all shadow-xs flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              Disconnect
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onConnect()}
              className="px-5 py-2.5 bg-[#3B82F6] hover:bg-[#2563EB] text-white rounded-xl text-xs font-bold transition-all shadow-xs flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              {busy ? "Redirecting…" : "Connect GitHub Account"}
            </button>
          )}

          <div className="flex items-center gap-2">
            <Link
              to="/repositories"
              className="flex-1 px-4 py-2 border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-semibold shadow-2xs flex items-center justify-center gap-1.5 transition-all"
            >
              <svg className="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              Browse Repositories
            </Link>
            <Link
              to="/audit"
              className="flex-1 px-4 py-2 border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-semibold shadow-2xs flex items-center justify-center gap-1.5 transition-all"
            >
              <svg className="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15.536a5 5 0 001.414 1.414m2.828-9.9a9 9 0 0112.728 0" />
              </svg>
              Run Audit
            </Link>
          </div>
        </div>
      </div>

      {/* Two Column Main Section */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Recent Audit Activity */}
        <div className="lg:col-span-7 rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">Recent Audit Activity</h2>
            <Link to="/audit" className="text-xs text-[#2563EB] font-bold hover:underline">
              View all
            </Link>
          </div>

          <div className="space-y-3 pt-1">
            {loadingKpis ? (
              Array.from({ length: 4 }).map((_, idx) => (
                <div key={idx} className="flex items-center justify-between p-3.5 rounded-xl border border-slate-100 bg-slate-50/20 animate-pulse">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-slate-200 shrink-0"></div>
                    <div className="space-y-2">
                      <div className="h-3 w-32 bg-slate-200 rounded"></div>
                      <div className="h-2.5 w-40 bg-slate-200 rounded"></div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="h-5 w-16 bg-slate-200 rounded-md"></div>
                    <div className="h-3 w-10 bg-slate-200 rounded"></div>
                  </div>
                </div>
              ))
            ) : recentActivityList.length === 0 ? (
              <div className="text-center py-10 text-xs text-slate-400 font-medium">
                No recent activity. Click "Run Audit" to scan a repository.
              </div>
            ) : (
              recentActivityList.map((item) => (
                <div key={item.id} className="flex items-center justify-between p-3.5 rounded-xl border border-slate-100 hover:border-slate-200 bg-slate-50/50 hover:bg-slate-50 transition-all">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                      item.status === "Completed" ? "bg-emerald-100 text-emerald-600" : item.status === "In Progress" ? "bg-amber-100 text-amber-600" : "bg-slate-100 text-slate-400"
                    }`}>
                      {item.status === "Completed" ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : item.status === "In Progress" ? (
                        <div className="w-2.5 h-2.5 rounded-full bg-amber-500 border border-white"></div>
                      ) : (
                        <div className="w-2.5 h-2.5 rounded-full bg-slate-400"></div>
                      )}
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-slate-900">{item.name}</h3>
                      <p className="text-[12px] text-slate-400 font-medium">{item.type}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <span className={`px-2.5 py-0.5 text-[12px] font-bold border rounded-md ${
                      item.status === "Completed"
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : item.status === "In Progress"
                        ? "bg-amber-50 text-amber-700 border-amber-200"
                        : "bg-slate-100 text-slate-600 border-slate-200"
                    }`}>
                      {item.status}
                    </span>
                    <span className="text-[13px] text-slate-400 font-medium">{item.time}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Issue Summary */}
        <div className="lg:col-span-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-6 flex flex-col">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">Issue Summary</h2>
            <Link to="/investigation" className="text-xs text-[#2563EB] font-bold hover:underline">
              View all
            </Link>
          </div>

          {loadingKpis ? (
            <div className="flex flex-col sm:flex-row items-center justify-around gap-6 py-4 animate-pulse">
              {/* Circular Graph Skeleton */}
              <div className="relative w-48 h-48 rounded-full border-[16px] border-slate-100 flex items-center justify-center">
                <div className="flex flex-col items-center justify-center text-center">
                  <div className="h-7 w-12 bg-slate-200 rounded mb-1.5"></div>
                  <div className="h-3.5 w-16 bg-slate-200 rounded"></div>
                </div>
              </div>
              {/* Legend List Skeleton */}
              <div className="space-y-4 w-full max-w-[160px]">
                {Array.from({ length: 4 }).map((_, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <div className="w-3.5 h-3.5 rounded-full bg-slate-200 shrink-0"></div>
                    <div className="h-4 bg-slate-200 rounded w-16"></div>
                    <div className="h-4 bg-slate-200 rounded w-6 ml-auto"></div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* Dynamic SVG Donut Chart & Legend */
            <div className="flex flex-col sm:flex-row items-center justify-around gap-6 py-4">
              <div className="relative w-48 h-48 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                  <path
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke="#F1F5F9"
                    strokeWidth="3.8"
                  />
                  {pCritical > 0 && (
                    <path
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none"
                      stroke="#EF4444"
                      strokeWidth="3.8"
                      strokeDasharray={`${pCritical} ${100 - pCritical}`}
                      strokeDashoffset={offsetCritical}
                    />
                  )}
                  {pHigh > 0 && (
                    <path
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none"
                      stroke="#F97316"
                      strokeWidth="3.8"
                      strokeDasharray={`${pHigh} ${100 - pHigh}`}
                      strokeDashoffset={offsetHigh}
                    />
                  )}
                  {pMedium > 0 && (
                    <path
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none"
                      stroke="#FBBF24"
                      strokeWidth="3.8"
                      strokeDasharray={`${pMedium} ${100 - pMedium}`}
                      strokeDashoffset={offsetMedium}
                    />
                  )}
                  {pLow > 0 && (
                    <path
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none"
                      stroke="#3B82F6"
                      strokeWidth="3.8"
                      strokeDasharray={`${pLow} ${100 - pLow}`}
                      strokeDashoffset={offsetLow}
                    />
                  )}
                </svg>

                <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                  <span className="text-3xl font-extrabold text-slate-900 leading-none">{total}</span>
                  <span className="text-xs text-slate-400 font-semibold mt-1.5">Total Issues</span>
                </div>
              </div>

              {/* Legend List */}
              <div className="space-y-4 text-sm font-semibold">
                <div className="flex items-center gap-3">
                  <span className="w-3.5 h-3.5 rounded-full bg-[#EF4444]"></span>
                  <span className="text-slate-500 w-20">Critical</span>
                  <span className="text-slate-900 font-bold">{critical}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-3.5 h-3.5 rounded-full bg-[#F97316]"></span>
                  <span className="text-slate-500 w-20">High</span>
                  <span className="text-slate-900 font-bold">{high}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-3.5 h-3.5 rounded-full bg-[#FBBF24]"></span>
                  <span className="text-slate-500 w-20">Medium</span>
                  <span className="text-slate-900 font-bold">{medium}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-3.5 h-3.5 rounded-full bg-[#3B82F6]"></span>
                  <span className="text-slate-500 w-20">Low</span>
                  <span className="text-slate-900 font-bold">{low}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


