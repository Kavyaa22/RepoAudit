import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../services/api-client';
import { env } from '../../config/env';
import { TOKEN_STORAGE_KEY } from '../../lib/constants';
import { loadUserSettings } from '../../lib/user-settings';
import { cachePeek, cacheSet } from '../../lib/client-cache';
import { rejectDemos } from '../../lib/demo-filter';
import type { InvestigationPhase, InvestigationResult, IssueReportPayload } from './types';
import { IssueReportForm } from './ui/IssueReportForm';
import { InvestigationReportView } from './ui/InvestigationReportView';

const PHASE_COPY: Record<string, string> = {
  orient: 'Reading your report',
  locate: 'Searching the codebase',
  inspect: 'Inspecting likely files',
  diagnose: 'Finding the root cause',
  ask_or_act: 'Drafting a fix',
  verify: 'Checking the proposed fix',
  report: 'Writing the report',
};

const EXPECTED_PHASES = ['orient', 'locate', 'inspect', 'diagnose', 'ask_or_act', 'verify', 'report'];

function buildAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;
  const settings = loadUserSettings();
  if (settings.openrouterApiKey) headers['x-api-key'] = settings.openrouterApiKey;
  if (settings.model) headers['x-model'] = settings.model;
  return headers;
}

function formatWhen(iso?: string) {
  if (!iso) return 'Recently';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'Recently';
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

function statusLabel(status?: string) {
  if (status === 'SUCCESS') return { text: 'Resolved', className: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
  if (status === 'PARTIAL') return { text: 'Needs info', className: 'bg-amber-50 text-amber-700 border-amber-200' };
  return { text: 'Failed', className: 'bg-red-50 text-red-700 border-red-200' };
}

async function streamInvestigation(
  payload: IssueReportPayload,
  onEvent: (data: Record<string, unknown>) => void,
): Promise<InvestigationResult | null> {
  const res = await fetch(`${env.apiBaseUrl}/investigation/run/stream`, {
    method: 'POST',
    headers: buildAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `Investigation stream failed (${res.status})`);
  }

  const reader = res.body?.getReader();
  const decoder = new TextDecoder();
  if (!reader) throw new Error('Browser could not read the investigation stream.');

  let buffer = '';
  let finalResult: InvestigationResult | null = null;

  const handleLine = (line: string) => {
    if (!line.startsWith('data: ')) return;
    try {
      const data = JSON.parse(line.slice(6)) as Record<string, unknown>;
      onEvent(data);
      if (data.type === 'result' && data.result) {
        finalResult = data.result as InvestigationResult;
      }
      if (typeof data.error === 'string') {
        throw new Error(data.error);
      }
    } catch (err) {
      if (err instanceof SyntaxError) return;
      throw err;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) handleLine(line);
  }
  buffer += decoder.decode();
  for (const line of buffer.split('\n')) handleLine(line);
  return finalResult;
}

export default function InvestigationPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InvestigationResult | null>(null);
  const [continueId, setContinueId] = useState<string | null>(null);
  const [phaseHint, setPhaseHint] = useState<string>('');
  const [livePhases, setLivePhases] = useState<InvestigationPhase[]>([]);
  const [lastPayload, setLastPayload] = useState<IssueReportPayload | null>(null);
  const [history, setHistory] = useState<any[]>(() => rejectDemos(cachePeek<any[]>('investigations') ?? []));
  const [loadingHistory, setLoadingHistory] = useState(() => (cachePeek<any[]>('investigations') ?? []).length === 0);
  const [historyFilter, setHistoryFilter] = useState('all');

  const fetchHistory = async (opts?: { silent?: boolean }) => {
    if (!opts?.silent && (cachePeek<any[]>('investigations') ?? []).length === 0) {
      setLoadingHistory(true);
    }
    try {
      const resp = await apiClient.get<{ success: boolean; results: any[]; message: string }>('/investigation/list');
      if (resp.data.success && resp.data.results) {
        const items = rejectDemos(
          resp.data.results.map((item) => ({
            ...item,
            name: item.project_name,
            display_name: item.project_name,
          })),
        );
        cacheSet('investigations', items);
        setHistory(items);
      }
    } catch (err) {
      console.error('Failed to load investigation history:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const startFresh = () => {
    setResult(null);
    setContinueId(null);
    setLastPayload(null);
    setLivePhases([]);
    setPhaseHint('');
    setError(null);
  };

  const handleLoadHistoryItem = async (id: string) => {
    setLoading(true);
    setError(null);
    setContinueId(null);
    setLivePhases([]);
    setPhaseHint('Opening previous report…');
    try {
      const resp = await apiClient.get<{ success: boolean; result: InvestigationResult; message: string }>(
        `/investigation/${id}`,
      );
      if (resp.data.success && resp.data.result) {
        setResult(resp.data.result);
        const r = resp.data.result;
        const fromHistory = history.find((item) => item.investigation_id === id);
        setLastPayload({
          project_name: r.project_name,
          branch: fromHistory?.branch || 'main',
          issue_description: fromHistory?.issue_description || r.summary_verdict,
          investigation_id: r.investigation_id,
        });
      } else {
        setError(resp.data.message || 'Failed to load investigation details.');
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Server error loading investigation');
    } finally {
      setLoading(false);
      setPhaseHint('');
    }
  };

  const handleRunInvestigation = async (payload: IssueReportPayload) => {
    setLoading(true);
    setError(null);
    setLivePhases([]);
    setPhaseHint('Starting investigation…');
    setLastPayload(payload);
    try {
      const useContinue = Boolean(payload.investigation_id || continueId);
      const investigationId = payload.investigation_id || continueId || '';

      if (useContinue) {
        setPhaseHint('Updating the report with your new context…');
        const resp = await apiClient.post<{ success: boolean; result: InvestigationResult; message: string }>(
          `/investigation/${investigationId}/continue`,
          {
            feature_name: payload.feature_name,
            action_name: payload.action_name,
            expected_behavior: payload.expected_behavior,
            actual_behavior: payload.actual_behavior,
            environment: payload.environment,
            severity: payload.severity,
            issue_description: payload.issue_description,
            error_log: payload.error_log,
            live_artifacts: payload.live_artifacts,
            branch: payload.branch,
            project_name: payload.project_name,
            project_id: payload.project_id,
            repo_path: payload.repo_path,
          },
        );
        if (resp.data.success && resp.data.result) {
          setResult(resp.data.result);
          setContinueId(null);
          fetchHistory();
        } else {
          setError(resp.data.message || 'Failed to continue investigation');
        }
        return;
      }

      const streamed = await streamInvestigation(payload, (data) => {
        if (data.type === 'phase') {
          const phase: InvestigationPhase = {
            name: String(data.name || ''),
            status: (data.status as InvestigationPhase['status']) || 'completed',
            detail: String(data.detail || ''),
            duration_ms: typeof data.duration_ms === 'number' ? data.duration_ms : undefined,
          };
          setLivePhases((prev) => [...prev.filter((p) => p.name !== phase.name), phase]);
          setPhaseHint(`${PHASE_COPY[phase.name] || phase.name.replace(/_/g, ' ')}`);
        } else if (data.type === 'started') {
          setPhaseHint('Connected. Looking through the repository…');
        } else if (data.type === 'result') {
          setPhaseHint('Putting the report together…');
        }
      });

      if (streamed) {
        setResult(streamed);
        setContinueId(null);
        fetchHistory();
      } else {
        setError('Investigation stream completed without a result payload.');
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Server error running investigation');
    } finally {
      setLoading(false);
      setPhaseHint('');
    }
  };

  const repoBranchOptions = useMemo(() => {
    const options = new Map<string, string>();
    for (const item of history) {
      const repo = String(item.project_name || 'Repository');
      const branch = String(item.branch || 'main');
      const key = `${repo}@@${branch}`;
      options.set(key, `${repo} / ${branch}`);
    }
    return Array.from(options.entries());
  }, [history]);

  const filteredHistory = useMemo(() => {
    if (historyFilter === 'all') return history;
    const [repo, branch] = historyFilter.split('@@');
    return history.filter(
      (item) => String(item.project_name || 'Repository') === repo && String(item.branch || 'main') === branch,
    );
  }, [history, historyFilter]);

  const showForm = !loading && (!result || Boolean(continueId));
  const showReport = !loading && Boolean(result) && !continueId;
  const lastDonePhaseIndex = EXPECTED_PHASES.reduce(
    (acc, name, index) => (livePhases.some((phase) => phase.name === name) ? index : acc),
    -1,
  );
  const activePhaseIndex = Math.min(EXPECTED_PHASES.length - 1, lastDonePhaseIndex + 1);

  return (
    <div className="space-y-6 pb-8">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Issue Investigator</h1>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            Point us at a repo, describe the bug, and get a root cause with a suggested fix.
          </p>
        </div>
        {(result || continueId) && (
          <button
            type="button"
            onClick={startFresh}
            className="px-3.5 py-2 border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-bold shadow-2xs transition-all cursor-pointer"
          >
            New issue
          </button>
        )}
      </div>

      {error && (
        <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 font-medium flex items-start justify-between gap-3">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-xs text-red-600 font-bold hover:underline cursor-pointer shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-8 space-y-6">
          {loading && (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-5">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#3B82F6] animate-pulse" />
                  <h2 className="text-base font-bold text-slate-900 m-0">Working on it</h2>
                </div>
                <p className="text-xs text-slate-500 font-medium m-0">
                  {phaseHint || 'Investigating the repository…'}
                </p>
                {lastPayload && (
                  <p className="text-[12px] text-slate-400 font-medium m-0 pt-1">
                    {lastPayload.project_name}
                    {lastPayload.branch ? ` · ${lastPayload.branch}` : ''}
                  </p>
                )}
              </div>

              <ol className="space-y-2">
                {EXPECTED_PHASES.map((name, index) => {
                  const recorded = livePhases.find((phase) => phase.name === name);
                  const isDone = Boolean(recorded);
                  const isActive = !isDone && index === activePhaseIndex;
                  return (
                    <li
                      key={name}
                      className={`flex items-start gap-3 rounded-xl border px-3.5 py-3 ${
                        isDone
                          ? 'border-emerald-100 bg-emerald-50/40'
                          : isActive
                            ? 'border-blue-100 bg-[#EEF2FF]'
                            : 'border-slate-100 bg-slate-50/50'
                      }`}
                    >
                      <span
                        className={`mt-0.5 w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-[11px] font-bold ${
                          isDone
                            ? 'bg-emerald-500 text-white'
                            : isActive
                              ? 'bg-[#3B82F6] text-white'
                              : 'bg-slate-200 text-slate-500'
                        }`}
                      >
                        {isDone ? (
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                          </svg>
                        ) : isActive ? (
                          <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                        ) : (
                          index + 1
                        )}
                      </span>
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-slate-800">{PHASE_COPY[name]}</div>
                        {recorded?.detail && (
                          <div className="text-[12px] text-slate-500 font-medium leading-relaxed mt-0.5 line-clamp-2">
                            {recorded.detail}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}

          {continueId && result && !loading && (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[12px] font-bold uppercase tracking-wider text-slate-400">Previous finding</div>
                <p className="text-xs text-slate-700 font-medium leading-relaxed m-0 mt-1 line-clamp-3">
                  {result.summary_verdict}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setContinueId(null)}
                className="text-xs text-[#2563EB] font-bold hover:underline cursor-pointer shrink-0"
              >
                Back to report
              </button>
            </div>
          )}

          {showForm && (
            <IssueReportForm
              onSubmit={handleRunInvestigation}
              loading={loading}
              continueInvestigationId={continueId}
              initialValues={continueId ? lastPayload : null}
            />
          )}

          {showReport && result && (
            <div className="space-y-4">
              <InvestigationReportView
                result={result}
                onContinue={() => {
                  setContinueId(result.investigation_id);
                  setLastPayload((prev) => ({
                    project_name: result.project_name,
                    branch: prev?.branch || 'main',
                    feature_name: prev?.feature_name,
                    action_name: prev?.action_name,
                    expected_behavior: prev?.expected_behavior,
                    actual_behavior: prev?.actual_behavior,
                    environment: prev?.environment,
                    severity: prev?.severity,
                    issue_description: prev?.issue_description || result.summary_verdict,
                    error_log: prev?.error_log || '',
                    investigation_id: result.investigation_id,
                  }));
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            </div>
          )}
        </div>

        <div className="lg:col-span-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4 lg:sticky lg:top-6">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-base font-bold text-slate-900 m-0">Recent issues</h2>
              {loadingHistory && (
                <div className="w-3.5 h-3.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
              )}
            </div>

            {repoBranchOptions.length > 0 && (
              <select
                value={historyFilter}
                onChange={(e) => setHistoryFilter(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2.5 text-xs text-slate-800 outline-none focus:bg-white focus:border-[#3B82F6]"
              >
                <option value="all">All repositories</option>
                {repoBranchOptions.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            )}

            <div className="space-y-2 max-h-[38rem] overflow-y-auto pr-1">
              {filteredHistory.length === 0 ? (
                <div className="text-center py-10 px-3">
                  <p className="text-xs text-slate-500 font-semibold m-0">
                    {history.length === 0 ? 'No investigations yet' : 'Nothing for this repository and branch'}
                  </p>
                  <p className="text-[12px] text-slate-400 font-medium mt-1 m-0">
                    {history.length === 0
                      ? 'Run one from the left — repo, branch, and a short description is enough.'
                      : 'Try another filter, or start a new issue.'}
                  </p>
                </div>
              ) : (
                filteredHistory.map((item) => {
                  const active = result?.investigation_id === item.investigation_id;
                  const badge = statusLabel(item.status);
                  const title = String(item.issue_description || item.summary_verdict || 'Untitled issue').trim();
                  return (
                    <button
                      key={item.investigation_id}
                      type="button"
                      disabled={loading}
                      onClick={() => handleLoadHistoryItem(item.investigation_id)}
                      className={`w-full text-left p-3.5 rounded-xl border transition-all cursor-pointer ${
                        active
                          ? 'border-[#3B82F6] bg-[#EEF2FF]'
                          : 'border-slate-200 hover:border-slate-300 bg-white hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-xs font-bold text-slate-900 leading-snug m-0 line-clamp-2">
                          {title || 'Untitled issue'}
                        </h3>
                        <span className={`px-2 py-0.5 text-[11px] font-bold border rounded-md shrink-0 ${badge.className}`}>
                          {badge.text}
                        </span>
                      </div>
                      <div className="mt-2 flex items-center gap-1.5 text-[12px] text-slate-500 font-medium">
                        <span className="truncate">{item.project_name || 'Repository'}</span>
                        <span className="text-slate-300">·</span>
                        <span className="font-mono truncate">{item.branch || 'main'}</span>
                      </div>
                      <div className="mt-1.5 text-[11px] text-slate-400 font-medium">{formatWhen(item.created_at)}</div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
