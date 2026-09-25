import { useCallback, useEffect, useMemo, useState } from "react";
import {
  generateDeadCodePrompt,
  getDeadCodeAudit,
  type DeadCodeAuditData,
  type DeadCodeFinding,
  type DeadCodePromptRequest,
} from "../lib/api";

interface Props {
  projectId: string;
}

type ConfidenceFilter = "ALL" | "HIGH" | "MEDIUM";
type CategoryFilter =
  | "ALL"
  | "unused_import"
  | "dead_function"
  | "dead_class"
  | "orphan_file"
  | "unused_dependency"
  | "empty_folder";

const CATEGORY_LABELS: Record<string, string> = {
  unused_import: "Unused Import",
  dead_function: "Dead Function",
  dead_class: "Dead Class",
  orphan_file: "Orphan File",
  unused_dependency: "Unused Dependency",
  empty_folder: "Empty Folder",
};

export default function DeadCodePromptPanel({ projectId }: Props) {
  const [audit, setAudit] = useState<DeadCodeAuditData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>("ALL");
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("ALL");
  const [promptModal, setPromptModal] = useState<{ text: string; title: string } | null>(null);
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getDeadCodeAudit(projectId)
      .then((data) => {
        if ("error" in data) {
          setError(typeof data.error === "string" ? data.error : "Could not load dead code audit");
          setAudit(null);
        } else {
          setAudit(data);
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load dead code audit");
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  const filteredFindings = useMemo(() => {
    if (!audit?.findings) return [];
    return audit.findings.filter((f) => {
      if (confidenceFilter !== "ALL" && f.confidence_level !== confidenceFilter) return false;
      if (categoryFilter !== "ALL" && f.category !== categoryFilter) return false;
      return true;
    });
  }, [audit, confidenceFilter, categoryFilter]);

  const openPrompt = useCallback(async (req: DeadCodePromptRequest, title: string) => {
    setGenerating(true);
    try {
      const res = await generateDeadCodePrompt(projectId, req);
      setPromptModal({ text: res.prompt, title });
      setCopied(false);
    } catch (err) {
      setPromptModal({
        text: err instanceof Error ? err.message : "Failed to generate prompt",
        title: "Error",
      });
    } finally {
      setGenerating(false);
    }
  }, [projectId]);

  const handleCopy = async () => {
    if (!promptModal?.text) return;
    await navigator.clipboard.writeText(promptModal.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleBatchPrompt = () => {
    if (filteredFindings.length === 0) return;
    void openPrompt(
      {
        finding_indices: filteredFindings.map((f) => f.index),
        confidence: confidenceFilter === "ALL" ? undefined : confidenceFilter,
        category: categoryFilter === "ALL" ? undefined : categoryFilter,
      },
      `IDE Prompt — ${filteredFindings.length} finding(s)`,
    );
  };

  if (loading) {
    return (
      <div className="mb-8 p-4 rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-500 animate-pulse">
        Loading dead code remediation tools…
      </div>
    );
  }

  if (error || !audit) {
    return null;
  }

  if (audit.total_findings === 0) {
    return null;
  }

  return (
    <div className="mb-10 rounded-xl border border-amber-200 bg-amber-50/50 overflow-hidden">
      <div className="px-5 py-4 border-b border-amber-200 bg-amber-50 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-amber-900 flex items-center gap-2">
            <span>🛠️</span> Optional: Generate IDE Agent Prompts
          </h3>
          <p className="text-xs text-amber-800/80 mt-0.5">
            Copy a prompt for Cursor/Copilot to re-verify and safely remove dead code. No LLM cost.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={confidenceFilter}
            onChange={(e) => setConfidenceFilter(e.target.value as ConfidenceFilter)}
            className="text-xs border border-amber-300 rounded-md px-2 py-1.5 bg-white text-slate-700"
          >
            <option value="ALL">All confidence</option>
            <option value="HIGH">HIGH only</option>
            <option value="MEDIUM">MEDIUM only</option>
          </select>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value as CategoryFilter)}
            className="text-xs border border-amber-300 rounded-md px-2 py-1.5 bg-white text-slate-700"
          >
            <option value="ALL">All categories</option>
            {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
          <button
            type="button"
            disabled={generating || filteredFindings.length === 0}
            onClick={handleBatchPrompt}
            className="text-xs font-semibold px-3 py-1.5 rounded-md bg-amber-600 hover:bg-amber-700 text-white disabled:opacity-50 transition-colors"
          >
            {generating ? "Generating…" : `Copy prompt (${filteredFindings.length})`}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-white/80 text-slate-600">
            <tr>
              <th className="text-left py-2.5 px-4 font-semibold">File</th>
              <th className="text-left py-2.5 px-4 font-semibold">Symbol</th>
              <th className="text-left py-2.5 px-4 font-semibold">Category</th>
              <th className="text-left py-2.5 px-4 font-semibold">Confidence</th>
              <th className="text-right py-2.5 px-4 font-semibold">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-amber-100 bg-white/40">
            {filteredFindings.map((f) => (
              <FindingRow
                key={`${f.index}-${f.path}-${f.symbol_name}`}
                finding={f}
                generating={generating}
                onGenerate={() =>
                  void openPrompt(
                    { finding_index: f.index },
                    `IDE Prompt — ${f.symbol_name}`,
                  )
                }
              />
            ))}
            {filteredFindings.length === 0 && (
              <tr>
                <td colSpan={5} className="py-6 px-4 text-center text-slate-500">
                  No findings match the selected filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {promptModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
          <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[85vh] flex flex-col border border-slate-200">
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
              <h4 className="font-bold text-slate-900 text-sm">{promptModal.title}</h4>
              <button
                type="button"
                onClick={() => setPromptModal(null)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none"
              >
                ×
              </button>
            </div>
            <div className="p-5 overflow-y-auto flex-1">
              <pre className="text-xs text-slate-700 whitespace-pre-wrap font-mono bg-slate-50 p-4 rounded-lg border border-slate-200">
                {promptModal.text}
              </pre>
            </div>
            <div className="px-5 py-4 border-t border-slate-200 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPromptModal(null)}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-md"
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => void handleCopy()}
                className="px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-md"
              >
                {copied ? "Copied!" : "Copy to clipboard"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FindingRow({
  finding,
  generating,
  onGenerate,
}: {
  finding: DeadCodeFinding;
  generating: boolean;
  onGenerate: () => void;
}) {
  const confClass =
    finding.confidence_level === "HIGH"
      ? "bg-red-50 text-red-700 border-red-200"
      : "bg-amber-50 text-amber-700 border-amber-200";

  return (
    <tr className="hover:bg-amber-50/60">
      <td className="py-3 px-4 font-mono text-slate-700 break-all text-xs" title={finding.path}>
        {finding.path}
      </td>
      <td className="py-3 px-4 font-mono font-semibold text-slate-800 break-words text-xs">{finding.symbol_name}</td>
      <td className="py-3 px-4 text-slate-600 whitespace-nowrap">
        {CATEGORY_LABELS[finding.category] || finding.category}
      </td>
      <td className="py-3 px-4 whitespace-nowrap">
        <span className={`inline-flex px-2 py-0.5 rounded border text-[12px] font-bold ${confClass}`}>
          {finding.confidence_level} ({finding.confidence_score}%)
        </span>
      </td>
      <td className="py-2.5 px-4 text-right">
        <button
          type="button"
          disabled={generating}
          onClick={onGenerate}
          className="text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline disabled:opacity-50"
        >
          Copy prompt
        </button>
      </td>
    </tr>
  );
}
