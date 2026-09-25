import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  getCachedGitHubRepos,
  getCachedGitHubStatus,
  getGitHubStatus,
  importRepository,
  listGitHubBranches,
  listGitHubRepos,
  type GitHubBranch,
  type GitHubRepo,
  type GitHubStatus,
  type ImportResult,
} from "../../../services/github";
import { Skeleton } from "../../../components/Skeleton";

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

export default function RepositoriesPage() {
  const [status, setStatus] = useState<GitHubStatus | null>(() => getCachedGitHubStatus());
  const [repos, setRepos] = useState<GitHubRepo[]>(() => getCachedGitHubRepos() ?? []);
  const [selected, setSelected] = useState<GitHubRepo | null>(null);
  const [branches, setBranches] = useState<GitHubBranch[]>([]);
  const [branch, setBranch] = useState("main");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(() => !getCachedGitHubStatus());
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastImport, setLastImport] = useState<ImportResult | null>(null);

  const refresh = useCallback(async () => {
    const hasCache = Boolean(getCachedGitHubStatus());
    if (!hasCache) setLoading(true);
    setError(null);
    try {
      const next = await getGitHubStatus();
      setStatus(next);
      if (next.connected) {
        const items = await listGitHubRepos();
        setRepos(items);
        if (items.length > 0 && !selected) {
          setSelected(items[0]);
        }
      } else {
        setRepos([]);
        setSelected(null);
        setBranches([]);
      }
    } catch (err) {
      setStatus({ connected: false });
      setRepos([]);
      setSelected(null);
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    void (async () => {
      try {
        const data = await listGitHubBranches(selected.owner, selected.name);
        if (cancelled) return;
        setBranches(data.items);
        setBranch(data.default_branch || selected.default_branch || "main");
      } catch (err) {
        if (!cancelled) setError(apiErrorMessage(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return repos;
    return repos.filter(
      (r) =>
        r.full_name.toLowerCase().includes(q) ||
        (r.description || "").toLowerCase().includes(q),
    );
  }, [repos, filter]);

  async function onImport() {
    if (!selected) return;
    setImporting(true);
    setError(null);
    setLastImport(null);
    try {
      const result = await importRepository({
        owner: selected.owner,
        repo: selected.name,
        branch,
        display_name: selected.name,
      });
      setLastImport(result);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-8">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Repositories</h1>
        <p className="text-xs text-slate-500 font-medium mt-0.5">
          Select a repository and branch to import for static structure analysis.
        </p>
      </div>

      {error && status?.connected && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3.5 text-xs text-red-700 font-medium">
          {error}
        </div>
      )}

      {!status?.connected && !loading && (
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center max-w-md mx-auto space-y-3 shadow-2xs">
          <h2 className="text-base font-bold text-slate-900">GitHub Not Connected</h2>
          <p className="text-xs text-slate-500">Connect your account on the Dashboard to access repositories.</p>
          <Link
            to="/dashboard"
            className="inline-block px-5 py-2.5 bg-[#3B82F6] hover:bg-[#2563EB] text-white text-xs font-bold rounded-xl shadow-xs transition-all"
          >
            Go to Dashboard &rarr;
          </Link>
        </div>
      )}

      {status?.connected && (
        <>
          {/* Search & Filter */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search repositories…"
              className="w-full sm:w-80 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs text-slate-800 outline-none focus:border-[#3B82F6] focus:ring-2 focus:ring-[#EEF2FF] transition-all"
            />
            <div className="text-xs text-slate-500 font-medium">
              {filtered.length} Repositories {status.github_login && `(@${status.github_login})`}
            </div>
          </div>

          {/* Split Pane */}
          <div className="grid gap-6 lg:grid-cols-12">
            {/* Left Pane */}
            <div className="lg:col-span-5 rounded-2xl border border-slate-200 bg-white overflow-hidden flex flex-col max-h-[30rem] shadow-2xs">
              <div className="px-4 py-3 bg-slate-50/80 border-b border-slate-200 text-xs font-bold text-slate-700">
                Connected Repositories
              </div>
              <ul className="divide-y divide-slate-100 overflow-y-auto flex-1 text-xs">
                {loading ? (
                  Array.from({ length: 6 }).map((_, idx) => (
                    <li key={idx} className="p-3.5 space-y-2">
                      <Skeleton className="h-3.5 w-40" />
                      <Skeleton className="h-3 w-64" />
                    </li>
                  ))
                ) : filtered.length === 0 ? (
                  <li className="p-4 text-center text-slate-400">No repositories found.</li>
                ) : (
                  filtered.map((repo) => {
                    const isSelected = selected?.id === repo.id;
                    return (
                      <li key={repo.id}>
                        <button
                          type="button"
                          onClick={() => setSelected(repo)}
                          className={`w-full text-left p-3.5 transition-all cursor-pointer ${
                            isSelected
                              ? "bg-[#EEF2FF] font-bold text-[#2563EB]"
                              : "hover:bg-slate-50 text-slate-800"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate">{repo.full_name}</span>
                            <span className="text-[12px] text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200 font-medium">
                              {repo.private ? "Private" : "Public"}
                            </span>
                          </div>
                          {repo.description && (
                            <p className="text-[13px] text-slate-500 mt-1 line-clamp-1 font-normal">{repo.description}</p>
                          )}
                        </button>
                      </li>
                    );
                  })
                )}
              </ul>
            </div>

            {/* Right Pane */}
            <div className="lg:col-span-7 rounded-2xl border border-slate-200 bg-white p-6 space-y-5 shadow-2xs">
              {selected ? (
                <>
                  <div className="pb-3 border-b border-slate-200 space-y-1">
                    <div className="flex items-center justify-between">
                      <h2 className="text-base font-bold text-slate-900">{selected.full_name}</h2>
                      <a
                        href={selected.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-[#2563EB] font-bold hover:underline"
                      >
                        GitHub &rarr;
                      </a>
                    </div>
                    {selected.description && (
                      <p className="text-xs text-slate-500 leading-relaxed">{selected.description}</p>
                    )}
                  </div>

                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-slate-700 block">Target Branch</label>
                      <select
                        value={branch}
                        onChange={(e) => setBranch(e.target.value)}
                        className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-xs text-slate-800 outline-none focus:bg-white focus:border-[#3B82F6]"
                      >
                        {branches.length === 0 ? (
                          <option value={branch}>{branch}</option>
                        ) : (
                          branches.map((b) => (
                            <option key={b.name} value={b.name}>
                              {b.name} {b.protected ? "(protected)" : ""}
                            </option>
                          ))
                        )}
                      </select>
                    </div>

                    <button
                      type="button"
                      disabled={importing}
                      onClick={() => void onImport()}
                      className="px-5 py-2.5 bg-[#3B82F6] hover:bg-[#2563EB] text-white text-xs font-bold rounded-xl shadow-xs transition-all disabled:opacity-50 cursor-pointer"
                    >
                      {importing ? "Importing…" : "Import Repository Branch"}
                    </button>
                  </div>

                  {lastImport && (
                    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs space-y-1 text-emerald-800">
                      <p className="font-bold">✓ {lastImport.message}</p>
                      <p className="text-slate-600">
                        {lastImport.owner}/{lastImport.repository_name} @ branch <span className="font-bold">{lastImport.branch}</span> ({lastImport.file_count} files)
                      </p>
                      <Link to="/audit" className="inline-block text-[#2563EB] font-bold hover:underline pt-1">
                        Go to Audit &rarr;
                      </Link>
                    </div>
                  )}
                </>
              ) : (
                <div className="p-8 text-center text-slate-400 text-xs">
                  Select a repository from the left list.
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}



