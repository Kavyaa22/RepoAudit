import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listProjects, getCachedProjects, type ProjectSummary } from "../../../services/projects";
import {
  getCachedGitHubRepos,
  getCachedGitHubStatus,
  getCachedGitHubBranches,
  getGitHubStatus,
  importRepository,
  listGitHubBranches,
  listGitHubRepos,
  type GitHubBranch,
  type GitHubRepo,
  type GitHubStatus,
} from "../../../services/github";
import {
  scanProject,
  streamScanProgress,
  getWiki,
  deleteAudit,
  getCachedAuditHistory,
  fetchMergedAuditHistory,
  type AuditHistoryRecord,
} from "../../../lib/api";
import { cacheSet } from "../../../lib/client-cache";
import { addAuditTombstones, itemMatchesTombstone, getAuditTombstoneIds } from "../../../lib/audit-history";
import { rejectDemos } from "../../../lib/demo-filter";
import { useWikiStore } from "../../../stores/wiki";
import ConfirmModal from "../../../components/ConfirmModal";
import { Skeleton, TableSkeleton } from "../../../components/Skeleton";

interface AuditHistoryItem {
  id: string;
  audit_id?: string;
  project_id?: string;
  name: string;
  status: string;
  error?: string;
  total_files: number;
  total_lines: number;
  created_at: string;
  score: number;
  is_valid: boolean;
  branch: string;
  structure_audit?: any;
  dead_code_audit?: any;
  security_audit?: any;
  wiki_summary?: any;
}

function toHistoryItem(r: AuditHistoryRecord): AuditHistoryItem {
  return {
    id: String(r.id || r.project_id || r.audit_id || ""),
    audit_id: r.audit_id,
    project_id: r.project_id,
    name: r.name,
    status: r.status,
    error: r.error,
    total_files: r.total_files,
    total_lines: r.total_lines,
    created_at: r.created_at,
    score: r.score,
    is_valid: r.is_valid,
    branch: r.branch,
    structure_audit: r.structure_audit,
    dead_code_audit: r.dead_code_audit,
    security_audit: r.security_audit,
    wiki_summary: r.wiki_summary,
  };
}

function apiErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "response" in err) {
    const resp = (err as { response?: { data?: { detail?: { message?: string } | string; error?: { message?: string } } } }).response;
    const detail = resp?.data?.detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String(detail.message);
    }
    if (typeof detail === "string") return detail;
    if (resp?.data?.error?.message) return resp.data.error.message;
  }
  return err instanceof Error ? err.message : "Something went wrong";
}

export default function AuditPage() {
  const navigate = useNavigate();
  const progressHandle = useRef<{ close: () => void } | null>(null);
  const [githubStatus, setGithubStatus] = useState<GitHubStatus | null>(() => getCachedGitHubStatus());
  const [gitHubRepos, setGitHubRepos] = useState<GitHubRepo[]>(() => getCachedGitHubRepos() ?? []);
  const [importedProjects, setImportedProjects] = useState<ProjectSummary[]>(() => getCachedProjects());
  
  const [selectedRepoKey, setSelectedRepoKey] = useState<string>("");
  const [selectedBranch, setSelectedBranch] = useState<string>("main");
  const [branches, setBranches] = useState<GitHubBranch[]>([]);
  const [loadingBranches, setLoadingBranches] = useState(false);
  
  const [error, setError] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(() => !getCachedGitHubStatus());
  const [auditHistory, setAuditHistory] = useState<AuditHistoryItem[]>(() =>
    getCachedAuditHistory().map(toHistoryItem),
  );
  const [loadingHistory, setLoadingHistory] = useState(() => getCachedAuditHistory().length === 0);
  const [historyReady, setHistoryReady] = useState(() => getCachedAuditHistory().length > 0);
  const [refreshingHistory, setRefreshingHistory] = useState(false);
  const [deletingAuditId, setDeletingAuditId] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<AuditHistoryItem | null>(null);
  const [reauditConfirmOpen, setReauditConfirmOpen] = useState(false);
  const [pendingReauditInfo, setPendingReauditInfo] = useState<{ name: string; branch: string } | null>(null);

  const {
    loading,
    setLoading,
    scanProgress,
    addProgress,
    setProjectId,
    setProject,
    setWiki,
    setError: setScanError,
    reset,
  } = useWikiStore();

  const fetchAuditHistory = useCallback(async (opts?: { silent?: boolean; allowCacheFallback?: boolean }) => {
    const hasCache = getCachedAuditHistory().length > 0;
    if (!opts?.silent && !hasCache) {
      setLoadingHistory(true);
    } else if (hasCache) {
      setRefreshingHistory(true);
    }
    try {
      const merged = await fetchMergedAuditHistory({
        allowCacheFallback: opts?.allowCacheFallback !== false,
      });
      if (merged == null) return; // superseded by a newer fetch/delete
      const items = merged.map(toHistoryItem);
      cacheSet("audit_history", merged);
      setAuditHistory(items);
      setHistoryReady(true);
    } catch {
      // Keep whatever is already on screen (cache or previous fetch).
      if (!hasCache) setHistoryReady(false);
    } finally {
      setLoadingHistory(false);
      setRefreshingHistory(false);
    }
  }, []);

  const confirmDeleteAudit = useCallback(
    async (item: AuditHistoryItem) => {
      const identifiers = [item.audit_id, item.project_id, item.id].filter(Boolean) as string[];
      if (identifiers.length === 0) return;

      setDeletingAuditId(item.audit_id || item.id);
      setError(null);
      try {
        const result = await deleteAudit(...identifiers);
        const tombstoneIds = [
          ...identifiers,
          ...result.deleted_ids,
          ...result.purged_project_ids,
        ];
        addAuditTombstones(tombstoneIds);
        const tombstones = getAuditTombstoneIds();
        setAuditHistory((current) => {
          const next = current.filter((entry) => !itemMatchesTombstone(entry, tombstones));
          cacheSet("audit_history", next);
          return next;
        });
        setConfirmTarget(null);
        await fetchAuditHistory({ silent: true, allowCacheFallback: false });
      } catch (err) {
        setError(apiErrorMessage(err));
      } finally {
        setDeletingAuditId(null);
      }
    },
    [fetchAuditHistory],
  );

  const handleDeleteAudit = useCallback(
    (item: AuditHistoryItem) => {
      setConfirmTarget(item);
    },
    [],
  );

  const refreshRepos = useCallback(async () => {
    setLoadingList(!getCachedGitHubStatus() && gitHubRepos.length === 0);
    setError(null);
    try {
      const [ghStatus, projectsList] = await Promise.all([
        getGitHubStatus().catch(() => ({ connected: false })),
        listProjects().catch(() => []),
      ]);

      setGithubStatus(ghStatus);
      const visibleProjects = rejectDemos(projectsList);
      setImportedProjects(visibleProjects);

      let reposList: GitHubRepo[] = [];
      if (ghStatus.connected) {
        reposList = rejectDemos(await listGitHubRepos().catch(() => []));
        setGitHubRepos(reposList);
      } else {
        setGitHubRepos([]);
      }

      if (ghStatus.connected && reposList.length > 0) {
        const first = reposList[0];
        setSelectedRepoKey(`github:${first.owner}/${first.name}`);
        setSelectedBranch(first.default_branch || "main");
      } else {
        setSelectedRepoKey("");
        setSelectedBranch("main");
      }
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void refreshRepos();
    void fetchAuditHistory();
  }, [refreshRepos, fetchAuditHistory]);

  useEffect(() => {
    return () => {
      progressHandle.current?.close();
    };
  }, []);

  const isGitHubRepoSelected = selectedRepoKey.startsWith("github:");
  const selectedGitHubRepo = isGitHubRepoSelected
    ? gitHubRepos.find(
        (r) => `github:${r.owner}/${r.name}` === selectedRepoKey
      ) ?? null
    : null;

  const selectedImportedProject = !isGitHubRepoSelected
    ? importedProjects.find(
        (p) => `imported:${p.project_id}` === selectedRepoKey
      ) ?? null
    : null;

  useEffect(() => {
    if (!selectedRepoKey) return;

    if (selectedGitHubRepo) {
      const cached = getCachedGitHubBranches(selectedGitHubRepo.owner, selectedGitHubRepo.name);
      if (cached?.items?.length) {
        setBranches(cached.items);
        setSelectedBranch(cached.default_branch || selectedGitHubRepo.default_branch || "main");
        setLoadingBranches(false);
      } else {
        setSelectedBranch(selectedGitHubRepo.default_branch || "main");
        setLoadingBranches(true);
      }
      listGitHubBranches(selectedGitHubRepo.owner, selectedGitHubRepo.name)
        .then((data) => {
          setBranches(data.items || []);
          if (data.default_branch) setSelectedBranch(data.default_branch);
        })
        .catch(() => {
          if (!cached?.items?.length) setBranches([]);
        })
        .finally(() => setLoadingBranches(false));
    } else if (selectedImportedProject) {
      setSelectedBranch(selectedImportedProject.default_branch || "main");
      if (selectedImportedProject.owner && selectedImportedProject.repository_name) {
        const cached = getCachedGitHubBranches(
          selectedImportedProject.owner,
          selectedImportedProject.repository_name,
        );
        if (cached?.items?.length) {
          setBranches(cached.items);
          setSelectedBranch(cached.default_branch || selectedImportedProject.default_branch || "main");
          setLoadingBranches(false);
        } else {
          setLoadingBranches(true);
        }
        listGitHubBranches(
          selectedImportedProject.owner,
          selectedImportedProject.repository_name
        )
          .then((data) => {
            setBranches(data.items || []);
            if (data.default_branch) setSelectedBranch(data.default_branch);
          })
          .catch(() => {
            if (!cached?.items?.length) setBranches([]);
          })
          .finally(() => setLoadingBranches(false));
      } else {
        setBranches([]);
      }
    }
  }, [selectedRepoKey]);

  function checkExistingAudit(): AuditHistoryItem | null {
    if (!historyReady) return null;
    if (!selectedRepoKey) return null;
    const targetBranch = (selectedBranch || "main").trim().toLowerCase();
    
    let targetName = "";
    let targetOwner = "";
    let targetRepo = "";
    let targetProjectId = "";

    if (selectedGitHubRepo) {
      targetName = selectedGitHubRepo.name.toLowerCase();
      targetOwner = selectedGitHubRepo.owner.toLowerCase();
      targetRepo = selectedGitHubRepo.name.toLowerCase();
    } else if (selectedImportedProject) {
      targetName = (selectedImportedProject.display_name || selectedImportedProject.repository_name || "").toLowerCase();
      targetOwner = (selectedImportedProject.owner || "").toLowerCase();
      targetRepo = (selectedImportedProject.repository_name || "").toLowerCase();
      targetProjectId = selectedImportedProject.project_id;
    }

    for (const item of auditHistory) {
      const itemBranch = (item.branch || "main").trim().toLowerCase();
      if (itemBranch !== targetBranch) continue;

      if (targetProjectId && (item.project_id === targetProjectId || item.id === targetProjectId)) {
        return item;
      }
      const itemName = (item.name || "").toLowerCase();
      if (targetRepo && itemName.includes(targetRepo)) {
        return item;
      }
      if (targetName && (itemName === targetName || itemName.replace(/[\s-_]/g, "") === targetName.replace(/[\s-_]/g, ""))) {
        return item;
      }
    }
    return null;
  }

  function handleStartAudit() {
    if (!selectedRepoKey) return;
    if (!historyReady || loadingHistory) {
      setError("Audit history is still loading. Please wait a moment, then try again.");
      return;
    }
    const existing = checkExistingAudit();
    if (existing) {
      const repoDisplayName = selectedGitHubRepo?.full_name || selectedImportedProject?.display_name || selectedGitHubRepo?.name || "this repository";
      setPendingReauditInfo({
        name: repoDisplayName,
        branch: selectedBranch || "main",
      });
      setReauditConfirmOpen(true);
      return;
    }
    void executeAudit();
  }

  async function executeAudit() {
    if (!selectedRepoKey) return;
    setReauditConfirmOpen(false);
    setPendingReauditInfo(null);
    reset();
    setLoading(true);
    setError(null);

    try {
      if (isGitHubRepoSelected && !githubStatus?.connected) {
        throw new Error(
          "GitHub is not connected. Please connect your GitHub account on the Dashboard to import and audit this repository."
        );
      }

      let scanUrl: string | undefined;
      let scanPath: string | undefined;
      let displayName: string | undefined;
      let owner: string | undefined;
      let repositoryName: string | undefined;
      let projectId: string | undefined;

      if (selectedGitHubRepo) {
        addProgress(`Importing repository ${selectedGitHubRepo.full_name} (${selectedBranch})...`);
        const imported = await importRepository({
          owner: selectedGitHubRepo.owner,
          repo: selectedGitHubRepo.name,
          branch: selectedBranch,
          display_name: selectedGitHubRepo.name,
        });
        scanUrl = imported.repository_url;
        scanPath = imported.workspace_path;
        projectId = imported.project_id;
        displayName = selectedGitHubRepo.full_name || selectedGitHubRepo.name;
        owner = selectedGitHubRepo.owner;
        repositoryName = selectedGitHubRepo.name;
      } else if (selectedImportedProject) {
        scanPath = selectedImportedProject.workspace_path || undefined;
        scanUrl = selectedImportedProject.repository_url || undefined;
        projectId = selectedImportedProject.project_id;
        displayName =
          selectedImportedProject.display_name ||
          (selectedImportedProject.owner && selectedImportedProject.repository_name
            ? `${selectedImportedProject.owner}/${selectedImportedProject.repository_name}`
            : undefined);
        owner = selectedImportedProject.owner || undefined;
        repositoryName = selectedImportedProject.repository_name || undefined;
      }

      const info = await scanProject({
        path: scanPath || undefined,
        url: scanUrl || undefined,
        display_name: displayName,
        branch: selectedBranch,
        owner,
        repository_name: repositoryName,
        project_id: projectId,
      });

      if (!info?.id) {
        throw new Error(
          info?.error ||
            "Could not start the audit scan. Please verify that your repository files are accessible and try again."
        );
      }
      setProjectId(info.id);
      setProject(info);

      progressHandle.current?.close();
      progressHandle.current = streamScanProgress(
        info.id,
        (step) => addProgress(step),
        async (status, errorMsg) => {
          if (status === "done") {
            const wiki = await getWiki(info.id);
            setWiki(wiki);
            setLoading(false);
            void fetchAuditHistory();
            navigate(`/project/${info.id}`);
          } else {
            setScanError("Scan failed");
            const last = [...useWikiStore.getState().scanProgress]
              .reverse()
              .find((s) => s.toLowerCase().includes("error"));
            const backendError = (errorMsg || "").trim();
            setError(
              backendError ||
                last?.replace(/^Error:\s*/i, "") ||
                "Audit failed. The scan was interrupted — try running it again.",
            );
            setLoading(false);
            void fetchAuditHistory();
          }
        },
      );
    } catch (err) {
      setError(apiErrorMessage(err));
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6 pb-8">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Repository Audits</h1>
        <p className="text-xs text-slate-500 font-medium mt-0.5">
          Run static structure and code quality audits for your repositories.
        </p>
      </div>

      {error && (
        <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 font-medium">
          {error}
        </div>
      )}

      {/* Audit Launcher Box */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-5">
        <h2 className="text-base font-bold text-slate-900">Run New Audit</h2>

        {loadingList ? (
          <div className="space-y-3 py-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : !githubStatus?.connected || gitHubRepos.length === 0 ? (
          <div className="rounded-xl bg-slate-50 p-4 space-y-2 border border-slate-200">
            <p className="text-xs text-slate-600">Connect your GitHub account to select repositories.</p>
            <Link to="/dashboard" className="text-xs text-[#2563EB] font-bold hover:underline">
              Connect GitHub Account &rarr;
            </Link>
          </div>
        ) : (
          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 block">Repository</label>
              <select
                value={selectedRepoKey}
                onChange={(e) => setSelectedRepoKey(e.target.value)}
                disabled={loading}
                className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-xs text-slate-800 outline-none focus:bg-white focus:border-[#3B82F6]"
              >
                {gitHubRepos.map((r) => (
                  <option key={`github:${r.owner}/${r.name}`} value={`github:${r.owner}/${r.name}`}>
                    {r.full_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 block">Branch</label>
              {loadingBranches ? (
                <div className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-400">
                  Loading branches…
                </div>
              ) : (
                <select
                  value={selectedBranch}
                  onChange={(e) => setSelectedBranch(e.target.value)}
                  disabled={loading}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-xs text-slate-800 outline-none focus:bg-white focus:border-[#3B82F6]"
                >
                  {branches.length === 0 ? (
                    <option value={selectedBranch}>{selectedBranch}</option>
                  ) : (
                    branches.map((b) => (
                      <option key={b.name} value={b.name}>
                        {b.name}
                      </option>
                    ))
                  )}
                </select>
              )}
            </div>

            <div className="md:col-span-2 pt-1">
              <button
                type="button"
                disabled={loading || !selectedRepoKey || !historyReady || loadingHistory}
                onClick={() => handleStartAudit()}
                className="px-5 py-2.5 bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow-xs cursor-pointer"
              >
                {loading
                  ? "Auditing Codebase…"
                  : !historyReady || loadingHistory
                    ? "Loading history…"
                    : "Run Audit"}
              </button>
            </div>

            {scanProgress.length > 0 && (
              <div className="md:col-span-2 rounded-xl border border-slate-200 bg-slate-900 text-slate-200 p-4 max-h-40 overflow-y-auto space-y-1 text-xs font-mono">
                {scanProgress.map((step, i) => (
                  <div key={`${i}-${step}`}>✓ {step}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Audit History Table */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900">Generated Audit Reports</h2>
          <div className="flex items-center gap-3">
            {refreshingHistory && (
              <span className="text-[11px] text-slate-400 font-medium">Refreshing…</span>
            )}
            <button
              onClick={() => void fetchAuditHistory()}
              className="text-xs text-[#2563EB] hover:underline font-bold"
            >
              Refresh
            </button>
          </div>
        </div>

        {loadingHistory ? (
          <TableSkeleton rows={5} cols={5} />
        ) : auditHistory.length === 0 ? (
          <p className="text-xs text-slate-500 py-4 text-center">No generated audit reports found.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-2xs">
            <table className="min-w-full text-left text-xs divide-y divide-slate-200">
              <thead>
                <tr className="bg-slate-50 text-[12px] font-bold text-slate-600 uppercase tracking-wider">
                  <th className="py-3 px-4">Repository</th>
                  <th className="py-3 px-4">Branch</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {auditHistory.map((item) => (
                  <tr key={item.audit_id || item.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3 px-4 font-bold text-slate-900">
                      {item.name || "Repository"}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-600">
                      {item.branch || "main"}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
                        item.status === "done"
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : item.status === "scanning"
                          ? "bg-blue-50 text-blue-700 border border-blue-200"
                          : "bg-red-50 text-red-700 border border-red-200"
                      }`}>
                        {item.status === "done" ? "Complete" : item.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-500">
                      {item.created_at ? new Date(item.created_at).toLocaleDateString() : "Recent"}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2 whitespace-nowrap">
                      {item.status === "done" && (
                        <button
                          onClick={() => navigate(`/project/${item.id}`)}
                          className="text-[#2563EB] font-bold hover:underline cursor-pointer"
                        >
                          View Report &rarr;
                        </button>
                      )}
                      <button
                        onClick={() => void handleDeleteAudit(item)}
                        disabled={deletingAuditId === (item.audit_id || item.id)}
                        className="text-red-600 hover:underline font-semibold disabled:opacity-50 cursor-pointer"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConfirmModal
        isOpen={reauditConfirmOpen}
        onClose={() => {
          setReauditConfirmOpen(false);
          setPendingReauditInfo(null);
        }}
        onConfirm={() => {
          void executeAudit();
        }}
        title="Re-audit Repository"
        message={`This repository branch (${pendingReauditInfo?.name || "this repository"} @ ${pendingReauditInfo?.branch || "main"}) has already been audited. Do you want to re-audit this again and overwrite the existing audit report?`}
        confirmText="Re-audit & Overwrite"
        isDestructive={false}
      />

      <ConfirmModal
        isOpen={Boolean(confirmTarget)}
        onClose={() => setConfirmTarget(null)}
        onConfirm={() => {
          if (confirmTarget) {
            void confirmDeleteAudit(confirmTarget);
          }
        }}
        title="Delete Audit Report"
        message={`Delete the audit for ${confirmTarget?.name || "this repository"}? This cannot be undone.`}
        confirmText="Delete"
        isDestructive={true}
      />
    </div>
  );
}

