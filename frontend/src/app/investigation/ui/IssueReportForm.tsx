import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { IssueReportPayload, LiveArtifactPayload } from '../types';
import {
  getCachedGitHubRepos,
  getCachedGitHubStatus,
  getCachedGitHubBranches,
  getGitHubStatus,
  listGitHubBranches,
  listGitHubRepos,
  type GitHubBranch,
  type GitHubRepo,
} from '../../../services/github';
import { listProjects, getCachedProjects, type ProjectSummary } from '../../../services/projects';
import { rejectDemos } from '../../../lib/demo-filter';
import { Skeleton } from '../../../components/Skeleton';

interface IssueReportFormProps {
  onSubmit: (payload: IssueReportPayload) => void;
  loading: boolean;
  continueInvestigationId?: string | null;
  initialValues?: Partial<IssueReportPayload> | null;
}

type ArtifactKind = LiveArtifactPayload['kind'];

const inputClass =
  'w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-xs text-slate-800 outline-none transition-all focus:bg-white focus:border-[#3B82F6] disabled:opacity-60';
const labelClass = 'text-xs font-semibold text-slate-700 block';

function matchRepoKey(
  projectName: string,
  gitHubRepos: GitHubRepo[],
  importedProjects: ProjectSummary[],
): string {
  const name = projectName.trim().toLowerCase();
  if (!name) return '';
  const gh = gitHubRepos.find(
    (r) => r.name.toLowerCase() === name || r.full_name.toLowerCase() === name,
  );
  if (gh) return `github:${gh.owner}/${gh.name}`;
  const imported = importedProjects.find((p) => p.display_name.toLowerCase() === name);
  if (imported) return `imported:${imported.project_id}`;
  return 'custom';
}

export function IssueReportForm({ onSubmit, loading, continueInvestigationId, initialValues }: IssueReportFormProps) {
  const [gitHubRepos, setGitHubRepos] = useState<GitHubRepo[]>(() => getCachedGitHubRepos() ?? []);
  const [isGitHubConnected, setIsGitHubConnected] = useState(() => Boolean(getCachedGitHubStatus()?.connected));
  const [selectedRepoKey, setSelectedRepoKey] = useState<string>('');
  const [projectName, setProjectName] = useState('');
  const [branch, setBranch] = useState('main');
  const [branches, setBranches] = useState<GitHubBranch[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(() => !getCachedGitHubStatus()?.connected);
  const [loadingBranches, setLoadingBranches] = useState(false);

  const [featureName, setFeatureName] = useState('');
  const [actionName, setActionName] = useState('');
  const [expectedBehavior, setExpectedBehavior] = useState('');
  const [actualBehavior, setActualBehavior] = useState('');
  const [environment, setEnvironment] = useState('');
  const [severity, setSeverity] = useState('medium');
  const [issueDescription, setIssueDescription] = useState('');
  const [errorLog, setErrorLog] = useState('');
  const [liveArtifactKind, setLiveArtifactKind] = useState<ArtifactKind>('network');
  const [liveArtifact, setLiveArtifact] = useState('');
  const [showExtra, setShowExtra] = useState(Boolean(continueInvestigationId));

  const preferredBranchRef = useRef<string | null>(null);
  const seededFromInitialRef = useRef(false);
  const userHasPickedRef = useRef(false);
  const branchFetchIdRef = useRef(0);

  useEffect(() => {
    if (!initialValues) return;
    if (initialValues.feature_name) setFeatureName(initialValues.feature_name);
    if (initialValues.action_name) setActionName(initialValues.action_name);
    if (initialValues.expected_behavior) setExpectedBehavior(initialValues.expected_behavior);
    if (initialValues.actual_behavior) setActualBehavior(initialValues.actual_behavior);
    if (initialValues.environment) setEnvironment(initialValues.environment);
    if (initialValues.severity) setSeverity(initialValues.severity);
    if (initialValues.issue_description) setIssueDescription(initialValues.issue_description);
    if (initialValues.error_log) setErrorLog(initialValues.error_log);
    if (initialValues.project_name) setProjectName(initialValues.project_name);
    if (initialValues.branch) {
      preferredBranchRef.current = initialValues.branch;
      setBranch(initialValues.branch);
    }
    if (initialValues.error_log || initialValues.expected_behavior || initialValues.actual_behavior) {
      setShowExtra(true);
    }
    seededFromInitialRef.current = true;
  }, [initialValues]);

  useEffect(() => {
    if (!initialValues?.project_name) return;
    const name = initialValues.project_name.trim().toLowerCase();
    const gh = gitHubRepos.find(
      (r) => r.name.toLowerCase() === name || r.full_name.toLowerCase() === name,
    );
    if (gh) {
      setSelectedRepoKey(`github:${gh.owner}/${gh.name}`);
    }
  }, [initialValues?.project_name, gitHubRepos]);

  const loadRepositories = useCallback(async () => {
    if (!getCachedGitHubStatus()?.connected && (getCachedGitHubRepos() ?? []).length === 0) {
      setLoadingRepos(true);
    }
    try {
      const ghStatus = await getGitHubStatus().catch(() => ({ connected: false }));
      setIsGitHubConnected(Boolean(ghStatus.connected));

      let reposList: GitHubRepo[] = [];
      if (ghStatus.connected) {
        reposList = rejectDemos(await listGitHubRepos().catch(() => []));
        setGitHubRepos(reposList);
      } else {
        setGitHubRepos([]);
      }

      if (seededFromInitialRef.current || userHasPickedRef.current) return;

      if (ghStatus.connected && reposList.length > 0) {
        const first = reposList[0];
        setSelectedRepoKey(`github:${first.owner}/${first.name}`);
        setProjectName(first.name);
        setBranch(first.default_branch || 'main');
      } else {
        setSelectedRepoKey('');
        setProjectName('');
        setBranch('main');
      }
    } catch {
      setSelectedRepoKey('');
      setProjectName('');
      setBranch('main');
    } finally {
      setLoadingRepos(false);
    }
  }, []);

  useEffect(() => {
    void loadRepositories();
  }, [loadRepositories]);

  useEffect(() => {
    if (!selectedRepoKey || !selectedRepoKey.startsWith('github:')) {
      setBranches([]);
      return;
    }

    const fetchId = ++branchFetchIdRef.current;

    const applyDefaultBranch = (next: string) => {
      if (preferredBranchRef.current) {
        setBranch(preferredBranchRef.current);
        return;
      }
      if (userHasPickedRef.current && branch) {
        return;
      }
      setBranch(next);
    };

    const target = gitHubRepos.find((r) => `github:${r.owner}/${r.name}` === selectedRepoKey);
    if (target) {
      setProjectName(target.name);
      const cached = getCachedGitHubBranches(target.owner, target.name);
      if (cached?.items?.length) {
        setBranches(cached.items);
        applyDefaultBranch(cached.default_branch || target.default_branch || 'main');
        setLoadingBranches(false);
      } else {
        applyDefaultBranch(target.default_branch || 'main');
        setLoadingBranches(true);
      }
      listGitHubBranches(target.owner, target.name)
        .then((data) => {
          if (branchFetchIdRef.current !== fetchId) return;
          setBranches(data.items || []);
          if (data.default_branch) applyDefaultBranch(data.default_branch);
        })
        .catch(() => {
          if (branchFetchIdRef.current !== fetchId) return;
          if (!cached?.items?.length) setBranches([]);
        })
        .finally(() => {
          if (branchFetchIdRef.current !== fetchId) return;
          setLoadingBranches(false);
        });
    }
  }, [selectedRepoKey, gitHubRepos]);

  const handleRepoChange = (value: string) => {
    userHasPickedRef.current = true;
    preferredBranchRef.current = null;
    setSelectedRepoKey(value);
  };

  const canSubmit = Boolean(issueDescription.trim() || continueInvestigationId) && Boolean(selectedRepoKey);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    const target = gitHubRepos.find((r) => `github:${r.owner}/${r.name}` === selectedRepoKey);
    const resolvedName = target?.name || projectName.trim() || 'Repository';

    const payload: IssueReportPayload = {
      project_name: resolvedName,
      branch: branch.trim() || 'main',
      feature_name: featureName,
      action_name: actionName,
      expected_behavior: expectedBehavior,
      actual_behavior: actualBehavior,
      environment,
      severity,
      issue_description: issueDescription.trim() || 'Continued investigation with additional evidence',
      error_log: errorLog,
      live_artifacts: liveArtifact.trim() ? [{ kind: liveArtifactKind, content: liveArtifact }] : [],
      investigation_id: continueInvestigationId || undefined,
      turn: continueInvestigationId ? 2 : 1,
    };

    onSubmit(payload);
  };

  const extraCount = [errorLog, expectedBehavior, actualBehavior, featureName, actionName, environment, liveArtifact]
    .filter((value) => value.trim()).length;

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-5">
      <div className="space-y-1">
        <h2 className="text-base font-bold text-slate-900 m-0">
          {continueInvestigationId ? 'Add more context' : 'Investigate an issue'}
        </h2>
        <p className="text-xs text-slate-500 font-medium m-0">
          {continueInvestigationId
            ? 'Paste a log, failed request, or anything that was missing last time. We will re-run on the same report.'
            : 'Choose the repository and branch, then describe what is broken. That is enough to start.'}
        </p>
      </div>

      {continueInvestigationId && (
        <div className="rounded-xl border border-blue-100 bg-[#EEF2FF] px-3.5 py-2.5 text-xs text-[#2563EB] font-medium">
          Continuing previous investigation
          <span className="ml-1.5 font-mono font-bold">{continueInvestigationId}</span>
        </div>
      )}

      {!isGitHubConnected || gitHubRepos.length === 0 ? (
        <div className="rounded-xl bg-slate-50 p-5 space-y-2 border border-slate-200">
          <p className="text-xs text-slate-700 font-semibold m-0">GitHub Not Connected</p>
          <p className="text-xs text-slate-500 m-0">
            Connect your GitHub account on the Dashboard to select and investigate issues in your repositories.
          </p>
          <Link
            to="/dashboard"
            className="inline-block px-4 py-2 bg-[#3B82F6] hover:bg-[#2563EB] text-white text-xs font-bold rounded-xl shadow-xs transition-all mt-1"
          >
            Connect GitHub Account &rarr;
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <label className={labelClass}>Repository</label>
            {loadingRepos ? (
              <Skeleton className="h-10 w-full rounded-xl" />
            ) : (
              <select
                value={selectedRepoKey}
                onChange={(e) => handleRepoChange(e.target.value)}
                disabled={loading}
                className={inputClass}
              >
                {gitHubRepos.map((r) => (
                  <option key={`github:${r.owner}/${r.name}`} value={`github:${r.owner}/${r.name}`}>
                    {r.full_name}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="space-y-1.5">
            <label className={labelClass}>Branch</label>
            {loadingBranches ? (
              <Skeleton className="h-10 w-full rounded-xl" />
            ) : (
              <select
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                disabled={loading}
                className={`${inputClass} font-mono`}
              >
                {branches.length === 0 ? (
                  <option value={branch}>{branch}</option>
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
        </div>
      )}

      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-3">
          <label className={labelClass}>
            What is broken? {!continueInvestigationId && <span className="text-red-500">*</span>}
          </label>
          <span className="text-[12px] text-slate-400 font-medium">
            {issueDescription.trim().length > 0 ? `${issueDescription.trim().length} characters` : 'A few sentences is enough'}
          </span>
        </div>
        <textarea
          rows={5}
          value={issueDescription}
          onChange={(e) => setIssueDescription(e.target.value)}
          required={!continueInvestigationId}
          disabled={loading}
          className={`${inputClass} min-h-[8.5rem] leading-relaxed resize-y`}
          placeholder="Example: Checkout succeeds, but the order never shows up in the dashboard after payment."
        />
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50/40 overflow-hidden">
        <button
          type="button"
          onClick={() => setShowExtra((open) => !open)}
          className="w-full flex items-center justify-between gap-3 px-3.5 py-3 text-left cursor-pointer hover:bg-slate-50 transition-colors"
        >
          <span className="text-xs font-semibold text-slate-700">
            Add logs or extra context
            {extraCount > 0 && (
              <span className="ml-2 px-1.5 py-0.5 rounded-md bg-white border border-slate-200 text-[11px] text-slate-500 font-bold">
                {extraCount} added
              </span>
            )}
          </span>
          <svg
            className={`w-4 h-4 text-slate-400 transition-transform ${showExtra ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showExtra && (
          <div className="px-3.5 pb-4 space-y-4 border-t border-slate-200 bg-white">
            <p className="text-[12px] text-slate-500 font-medium pt-3 m-0">
              Optional. A stack trace or failed request helps us land on the right file faster — the investigation still runs without it.
            </p>

            <div className="space-y-1.5">
              <label className={labelClass}>Error log or stack trace</label>
              <textarea
                rows={4}
                value={errorLog}
                onChange={(e) => setErrorLog(e.target.value)}
                disabled={loading}
                className={`${inputClass} font-mono bg-slate-50 leading-relaxed`}
                placeholder="Paste a console error, backend traceback, or exception…"
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1.5">
                <label className={labelClass}>Expected</label>
                <textarea
                  rows={2}
                  value={expectedBehavior}
                  onChange={(e) => setExpectedBehavior(e.target.value)}
                  disabled={loading}
                  className={inputClass}
                  placeholder="What should have happened"
                />
              </div>
              <div className="space-y-1.5">
                <label className={labelClass}>Actual</label>
                <textarea
                  rows={2}
                  value={actualBehavior}
                  onChange={(e) => setActualBehavior(e.target.value)}
                  disabled={loading}
                  className={inputClass}
                  placeholder="What happened instead"
                />
              </div>
              <div className="space-y-1.5">
                <label className={labelClass}>Feature</label>
                <input
                  type="text"
                  value={featureName}
                  onChange={(e) => setFeatureName(e.target.value)}
                  disabled={loading}
                  className={inputClass}
                  placeholder="auth, checkout, dashboard…"
                />
              </div>
              <div className="space-y-1.5">
                <label className={labelClass}>Last action</label>
                <input
                  type="text"
                  value={actionName}
                  onChange={(e) => setActionName(e.target.value)}
                  disabled={loading}
                  className={inputClass}
                  placeholder="clicked Pay, submitted login…"
                />
              </div>
              <div className="space-y-1.5">
                <label className={labelClass}>Environment</label>
                <input
                  type="text"
                  value={environment}
                  onChange={(e) => setEnvironment(e.target.value)}
                  disabled={loading}
                  className={inputClass}
                  placeholder="local, staging, Chrome…"
                />
              </div>
              <div className="space-y-1.5">
                <label className={labelClass}>Severity</label>
                <select value={severity} onChange={(e) => setSeverity(e.target.value)} disabled={loading} className={inputClass}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <label className={labelClass}>Failed request or extra evidence</label>
                <select
                  value={liveArtifactKind}
                  onChange={(e) => setLiveArtifactKind(e.target.value as ArtifactKind)}
                  disabled={loading}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[12px] text-slate-700 outline-none"
                >
                  <option value="network">Network</option>
                  <option value="console">Console</option>
                  <option value="backend_trace">Backend</option>
                  <option value="timing">Timing</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <textarea
                rows={3}
                value={liveArtifact}
                onChange={(e) => setLiveArtifact(e.target.value)}
                disabled={loading}
                className={`${inputClass} font-mono bg-slate-50`}
                placeholder="URL, status code, correlation ID, or a console line…"
              />
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3 pt-1">
        <button
          type="submit"
          disabled={loading || !canSubmit}
          className="px-5 py-2.5 bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow-xs cursor-pointer flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              {continueInvestigationId ? 'Updating investigation…' : 'Investigating…'}
            </>
          ) : continueInvestigationId ? (
            'Re-run with this context'
          ) : (
            'Investigate this issue'
          )}
        </button>
        {!continueInvestigationId && (
          <p className="text-[12px] text-slate-400 font-medium m-0">
            Repo, branch, and a description are all that is required.
          </p>
        )}
      </div>
    </form>
  );
}
