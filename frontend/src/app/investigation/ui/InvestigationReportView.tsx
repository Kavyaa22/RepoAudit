import { useState } from 'react';
import type { InvestigationResult, CodePatch } from '../types';

interface InvestigationReportViewProps {
  result: InvestigationResult;
  onContinue?: () => void;
}

const PHASE_COPY: Record<string, string> = {
  orient: 'Reading your report',
  locate: 'Searching the codebase',
  inspect: 'Opening likely files',
  diagnose: 'Identifying the cause',
  ask_or_act: 'Preparing actionable steps',
  verify: 'Checking suggested change',
  report: 'Generating report',
};

function confidenceLabel(level?: string) {
  if (level === 'HIGH') return 'High Confidence';
  if (level === 'MEDIUM') return 'Likely Cause';
  return 'Potential Cause';
}

function statusCopy(status: InvestigationResult['status'], needsMore: boolean) {
  if (status === 'SUCCESS') {
    return {
      label: 'Cause Identified & Ready to Fix',
      className: 'bg-emerald-50 text-emerald-800 border-emerald-200',
      border: 'border-emerald-200',
      dot: 'bg-emerald-500',
    };
  }
  if (status === 'FAILED') {
    return {
      label: 'Could not identify cause',
      className: 'bg-rose-50 text-rose-800 border-rose-200',
      border: 'border-rose-200',
      dot: 'bg-rose-500',
    };
  }
  return {
    label: needsMore ? 'Need a bit more detail' : 'Best Assessment — Review Before Applying',
    className: 'bg-amber-50 text-amber-800 border-amber-200',
    border: 'border-amber-200',
    dot: 'bg-amber-500',
  };
}

export function InvestigationReportView({ result, onContinue }: InvestigationReportViewProps) {
  const [selectedPatchIdx, setSelectedPatchIdx] = useState(0);
  const [copiedPatchId, setCopiedPatchId] = useState<string | null>(null);
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [checkedReproItems, setCheckedReproItems] = useState<Record<string, boolean>>({});
  const [showOthers, setShowOthers] = useState(false);
  const [showTrace, setShowTrace] = useState(false);

  const needsMore =
    result.status === 'PARTIAL' &&
    ((result.clarification_questions || []).length > 0 || result.evidence?.route === 'clarify');
  const status = statusCopy(result.status, needsMore);
  const primary = result.primary_root_cause;
  const otherCauses = (result.all_hypotheses || []).filter(
    (item) => item.hypothesis_id !== primary?.hypothesis_id,
  );
  const patches = result.code_patches || [];
  const activePatch: CodePatch | undefined = patches[selectedPatchIdx];
  const files = result.isolated_targets || [];
  const snapshotBits = (result.snapshot_label || result.project_name || '').split('@');
  const repoLabel = snapshotBits[0]?.trim() || result.project_name;
  const branchLabel = snapshotBits[1]?.replace(/\([^)]*\)/g, '').replace('branch', '').trim() || '';

  const handleCopyDiff = (diff: string, patchId: string) => {
    void navigator.clipboard.writeText(diff);
    setCopiedPatchId(patchId);
    setTimeout(() => setCopiedPatchId(null), 2500);
  };

  const generateAIPrompt = () => {
    const lines: string[] = [];
    lines.push(`I need your help fixing an issue in ${repoLabel}${branchLabel ? ` (branch: ${branchLabel})` : ''}:`);
    lines.push('');
    lines.push(`### Problem:`);
    lines.push(primary?.title || result.summary_verdict);
    lines.push('');
    lines.push(`### Root Cause:`);
    lines.push(primary?.description || result.summary_verdict);
    lines.push('');
    if (files.length > 0) {
      lines.push(`### Relevant Files:`);
      files.slice(0, 3).forEach((f) => lines.push(`- ${f.path}`));
      lines.push('');
    }
    if (result.remediation_steps.length > 0) {
      lines.push(`### Instructions to Fix:`);
      result.remediation_steps.forEach((step, i) => lines.push(`${i + 1}. ${step}`));
      lines.push('');
    }
    if (activePatch?.unified_diff) {
      lines.push(`### Suggested Code Change:`);
      lines.push('```diff');
      lines.push(activePatch.unified_diff);
      lines.push('```');
      lines.push('');
    }
    lines.push('Please apply this fix and ensure all related tests and functionality work properly.');
    return lines.join('\n');
  };

  return (
    <div className="space-y-5">
      {/* Header Banner */}
      <div className={`rounded-2xl border ${status.border} bg-white p-6 shadow-2xs`}>
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="space-y-2 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-2.5 py-1 border rounded-full text-[12px] font-bold flex items-center gap-1.5 ${status.className}`}>
                <span className={`w-2 h-2 rounded-full ${status.dot}`} />
                {status.label}
              </span>
              {primary && (
                <span className="px-2.5 py-1 bg-slate-50 text-slate-600 border border-slate-200 rounded-full text-[12px] font-semibold">
                  {confidenceLabel(primary.confidence_level)}
                </span>
              )}
            </div>
            <h2 className="text-lg font-extrabold text-slate-900 leading-snug m-0">
              {primary?.title || 'Investigation report'}
            </h2>
            <p className="text-xs text-slate-500 font-medium m-0">
              {repoLabel}
              {branchLabel ? ` · ${branchLabel}` : ''}
            </p>
          </div>
          {onContinue && result.status !== 'SUCCESS' && (
            <button
              type="button"
              onClick={onContinue}
              className="px-4 py-2 rounded-xl bg-[#3B82F6] hover:bg-[#2563EB] text-white text-xs font-bold shadow-xs cursor-pointer shrink-0"
            >
              Add more context
            </button>
          )}
        </div>
      </div>

      {/* AI Agent Copy-Paste Prompt Box */}
      <section className="rounded-2xl border border-blue-200 bg-linear-to-br from-blue-50/70 via-white to-indigo-50/40 p-6 shadow-2xs space-y-3.5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">🤖</span>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-blue-950 m-0">
                AI Agent Prompt (Ready to Copy)
              </h3>
              <p className="text-[12px] text-slate-500 font-medium m-0">
                Copy and paste this into Cursor, Claude, Windsurf, or Antigravity to fix the bug instantly.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard.writeText(generateAIPrompt());
              setCopiedPrompt(true);
              setTimeout(() => setCopiedPrompt(false), 2500);
            }}
            className="px-4 py-2 bg-[#3B82F6] hover:bg-[#2563EB] text-white rounded-xl text-xs font-bold flex items-center gap-2 cursor-pointer shadow-xs transition-all shrink-0"
          >
            {copiedPrompt ? (
              <>
                <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                Copied Prompt!
              </>
            ) : (
              <>
                <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                </svg>
                Copy Prompt for AI Agent
              </>
            )}
          </button>
        </div>

        <div className="rounded-xl border border-blue-100 bg-white/95 p-3.5 text-xs text-slate-700 font-mono leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto select-all shadow-inner">
          {generateAIPrompt()}
        </div>
      </section>

      {/* What Happened (Plain English) */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-base">💡</span>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 m-0">What is happening</h3>
        </div>
        <p className="text-sm text-slate-800 leading-relaxed font-medium m-0">{result.summary_verdict}</p>
        {primary?.description && primary.description !== result.summary_verdict && (
          <p className="text-xs text-slate-600 leading-relaxed m-0">{primary.description}</p>
        )}
      </section>

      {needsMore && (result.clarification_questions || []).length > 0 && (
        <section className="rounded-2xl border border-amber-200 bg-amber-50/60 p-6 shadow-2xs space-y-3">
          <h3 className="text-sm font-bold text-amber-950 m-0">To be more certain, add this</h3>
          <ul className="space-y-2 m-0 pl-0 list-none">
            {(result.clarification_questions || []).map((question, idx) => (
              <li key={idx} className="text-xs text-amber-950 font-medium leading-relaxed bg-white border border-amber-100 rounded-xl px-3.5 py-2.5">
                {question}
              </li>
            ))}
          </ul>
          {onContinue && (
            <button
              type="button"
              onClick={onContinue}
              className="text-xs font-bold text-[#2563EB] hover:underline cursor-pointer"
            >
              Add it and re-run →
            </button>
          )}
        </section>
      )}

      {/* Files to check */}
      {files.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-base">📁</span>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 m-0">Files to check first</h3>
          </div>
          <ul className="space-y-2 m-0 pl-0 list-none">
            {files.slice(0, 5).map((file) => (
              <li key={file.path} className="rounded-xl border border-slate-200 bg-slate-50/70 px-3.5 py-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs font-bold text-slate-800 break-all">{file.path}</div>
                  {file.matched_reason && (
                    <p className="text-[12px] text-slate-500 font-medium m-0 mt-1 leading-relaxed">{file.matched_reason}</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard.writeText(file.path);
                    setCopiedPatchId(`file:${file.path}`);
                    setTimeout(() => setCopiedPatchId(null), 2000);
                  }}
                  className="px-2.5 py-1 text-[11px] font-bold text-slate-600 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg shrink-0 cursor-pointer shadow-2xs transition-colors"
                >
                  {copiedPatchId === `file:${file.path}` ? 'Copied!' : 'Copy path'}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Step by Step Action Plan */}
      {result.remediation_steps.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-base">🛠️</span>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 m-0">Step-by-Step Fix Plan</h3>
          </div>
          <ol className="space-y-3 m-0 pl-0 list-none">
            {result.remediation_steps.map((step, idx) => (
              <li key={idx} className="flex gap-3">
                <span className="w-6 h-6 rounded-full bg-[#3B82F6] text-white text-[12px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                  {idx + 1}
                </span>
                <p className="text-xs text-slate-800 font-medium leading-relaxed m-0 pt-0.5">{step}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Suggested Code Diff */}
      {patches.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-2xs">
          <div className="px-6 py-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base">💻</span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 m-0">Suggested code change</h3>
              </div>
              {activePatch?.explanation && (
                <p className="text-xs text-slate-600 font-medium m-0 mt-1">{activePatch.explanation}</p>
              )}
            </div>
            {activePatch && (
              <button
                type="button"
                onClick={() => handleCopyDiff(activePatch.unified_diff, activePatch.patch_id)}
                className="px-3 py-1.5 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg text-xs font-bold text-slate-700 cursor-pointer"
              >
                {copiedPatchId === activePatch.patch_id ? 'Copied' : 'Copy diff'}
              </button>
            )}
          </div>
          {patches.length > 1 && (
            <div className="px-4 pt-3 flex gap-2 overflow-x-auto">
              {patches.map((patch, idx) => (
                <button
                  key={patch.patch_id}
                  type="button"
                  onClick={() => setSelectedPatchIdx(idx)}
                  className={`px-3 py-1.5 rounded-lg text-[12px] font-bold border cursor-pointer ${
                    selectedPatchIdx === idx
                      ? 'bg-[#EEF2FF] border-blue-200 text-[#2563EB]'
                      : 'bg-white border-slate-200 text-slate-600'
                  }`}
                >
                  {patch.file_path.split('/').pop()}
                </button>
              ))}
            </div>
          )}
          {activePatch && (
            <div className="bg-slate-950 overflow-x-auto text-xs font-mono leading-relaxed">
              <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-slate-400 text-[11px]">
                <span className="font-semibold text-slate-300">{activePatch.file_path}</span>
                <span>{activePatch.unified_diff.split('\n').length} lines</span>
              </div>
              <div className="p-3">
                {activePatch.unified_diff.split('\n').map((line, i) => {
                  let colorClass = 'text-slate-300';
                  if (line.startsWith('+') && !line.startsWith('+++')) {
                    colorClass = 'text-emerald-300 bg-emerald-950/50 font-semibold';
                  } else if (line.startsWith('-') && !line.startsWith('---')) {
                    colorClass = 'text-rose-300 bg-rose-950/50 font-semibold';
                  } else if (line.startsWith('@')) {
                    colorClass = 'text-sky-300 font-bold bg-sky-950/30';
                  }
                  return (
                    <div key={i} className={`flex items-start gap-3 px-2 py-0.5 rounded-sm ${colorClass}`}>
                      <span className="w-8 shrink-0 text-slate-600 text-right select-none text-[11px] font-mono">
                        {i + 1}
                      </span>
                      <span className="whitespace-pre-wrap break-all flex-1">{line}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {activePatch?.verification_summary && (
            <p className="px-6 py-3 text-[12px] text-slate-500 font-medium m-0 border-t border-slate-200">
              {activePatch.verification_summary}
            </p>
          )}
        </section>
      )}

      {/* Testing Checklist */}
      {(result.repro_checklist || []).length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-base">✅</span>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 m-0">How to test and verify</h3>
          </div>
          <div className="space-y-2">
            {(result.repro_checklist || []).map((step) => {
              const checked = !!checkedReproItems[step];
              return (
                <button
                  key={step}
                  type="button"
                  onClick={() => setCheckedReproItems((prev) => ({ ...prev, [step]: !prev[step] }))}
                  className={`w-full text-left p-3.5 border rounded-xl flex items-start gap-3 cursor-pointer ${
                    checked ? 'border-emerald-200 bg-emerald-50/40' : 'border-slate-200 bg-white'
                  }`}
                >
                  <span
                    className={`w-4 h-4 rounded-md border shrink-0 mt-0.5 flex items-center justify-center ${
                      checked ? 'bg-emerald-500 border-emerald-500' : 'border-slate-300 bg-white'
                    }`}
                  >
                    {checked && (
                      <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </span>
                  <span className={`text-xs font-medium leading-relaxed ${checked ? 'text-slate-400 line-through' : 'text-slate-700'}`}>
                    {step}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {otherCauses.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white shadow-2xs overflow-hidden">
          <button
            type="button"
            onClick={() => setShowOthers((open) => !open)}
            className="w-full px-6 py-4 flex items-center justify-between text-left cursor-pointer hover:bg-slate-50"
          >
            <span className="text-xs font-bold text-slate-700">Other possibilities</span>
            <span className="text-[12px] text-slate-400 font-semibold">{showOthers ? 'Hide' : 'Show'}</span>
          </button>
          {showOthers && (
            <div className="px-6 pb-5 space-y-3 border-t border-slate-100">
              {otherCauses.map((item) => (
                <div key={item.hypothesis_id} className="pt-3 space-y-1">
                  <div className="text-xs font-bold text-slate-800">
                    {item.title}
                    <span className="ml-2 font-semibold text-slate-400">{confidenceLabel(item.confidence_level)}</span>
                  </div>
                  <p className="text-[12px] text-slate-600 leading-relaxed m-0">{item.description}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {(result.phases || []).length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white shadow-2xs overflow-hidden">
          <button
            type="button"
            onClick={() => setShowTrace((open) => !open)}
            className="w-full px-6 py-4 flex items-center justify-between text-left cursor-pointer hover:bg-slate-50"
          >
            <span className="text-xs font-bold text-slate-700">Investigation Details</span>
            <span className="text-[12px] text-slate-400 font-semibold">{showTrace ? 'Hide' : 'Show'}</span>
          </button>
          {showTrace && (
            <ol className="px-6 pb-5 space-y-2 border-t border-slate-100 pt-4 m-0 pl-6 list-none">
              {result.phases.map((phase, idx) => (
                <li key={`${phase.name}-${idx}`} className="text-xs">
                  <span className="font-bold text-slate-800">{PHASE_COPY[phase.name] || phase.name.replace(/_/g, ' ')}</span>
                  {phase.detail && <span className="text-slate-500 font-medium"> — {phase.detail}</span>}
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  );
}
