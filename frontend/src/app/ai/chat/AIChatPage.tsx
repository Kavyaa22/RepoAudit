import { Navigate } from "react-router-dom";

/*
 * AI chat disabled — Issue Investigator is the primary workflow.
 * Original AIChatPage implementation preserved below for reference.
 *
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE, streamChat } from "../../../lib/api";
import { listProjects, type ProjectSummary } from "../../../services/projects";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function AIChatPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [loadingRepos, setLoadingRepos] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoadingRepos(true);
      try {
        const items = await listProjects();
        if (cancelled) return;
        setProjects(items);
        if (items.length > 0) {
          setSelectedId(items[0].project_id);
        }
      } catch {
        // Fallback
      } finally {
        if (!cancelled) setLoadingRepos(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedProj = projects.find((p) => p.project_id === selectedId);

  function handleSend() {
    if (!input.trim() || !selectedId || streaming) return;
    const question = input.trim();
    setInput("");

    setMessages((prev) => [
      ...prev,
      { role: "user", content: question },
      { role: "assistant", content: "" },
    ]);
    setStreaming(true);

    streamChat(
      selectedId,
      question,
      (data) => {
        if (data.content) {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last && last.role === "assistant") {
              next[next.length - 1] = {
                ...last,
                content: last.content + data.content,
              };
            }
            return next;
          });
        }
      },
      () => setStreaming(false),
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
      <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-sm">
            AI
          </div>
          <div>
            <h1 className="text-base font-bold text-slate-900">Codebase AI Assistant</h1>
            <p className="text-xs text-slate-500">Ask architectural and code questions for selected repo & branch</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase text-slate-500">Repository & Branch:</span>
            {loadingRepos ? (
              <span className="text-xs text-slate-400">Loading repos...</span>
            ) : projects.length === 0 ? (
              <span className="text-xs text-slate-500">No repos imported yet</span>
            ) : (
              <select
                value={selectedId}
                onChange={(e) => {
                  setSelectedId(e.target.value);
                  setMessages([]);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800 font-medium focus:border-blue-500 outline-none"
              >
                {projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.display_name} @ {p.default_branch || "main"}
                  </option>
                ))}
              </select>
            )}
          </label>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50/50">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center text-slate-400">
            <svg className="w-12 h-12 text-slate-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
            </svg>
            <p className="text-sm font-semibold text-slate-700">Select a repository and ask anything about the codebase</p>
            <p className="text-xs text-slate-500 mt-1 max-w-sm">
              Example: "Explain the folder architecture", "Where is authentication handled?", or "How do I run tests?"
            </p>
          </div>
        ) : (
          messages.map((m, idx) => (
            <div
              key={idx}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-2xl px-4 py-3 rounded-xl text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-blue-600 text-white rounded-br-none"
                    : "bg-white border border-slate-200 text-slate-800 rounded-bl-none shadow-xs"
                }`}
              >
                {m.content || (streaming && idx === messages.length - 1 ? "Thinking…" : "")}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="p-4 bg-white border-t border-slate-200">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-3 max-w-4xl mx-auto"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              selectedProj
                ? `Ask about ${selectedProj.display_name} @ ${selectedProj.default_branch || "main"}...`
                : "Select a repository to ask questions..."
            }
            disabled={!selectedId || streaming}
            className="flex-1 rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all disabled:bg-slate-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || !selectedId || streaming}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition-all shadow-xs"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
*/

export default function AIChatPage() {
  return <Navigate to="/investigation" replace />;
}
