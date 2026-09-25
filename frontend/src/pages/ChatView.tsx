import { Navigate } from "react-router-dom";

/*
 * AI chat disabled — Issue Investigator is the primary workflow.
 * Original ChatView implementation preserved below for reference.
 *
import { useState, useRef, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { streamChat } from "../lib/api";
import { useWikiStore, type ChatReference } from "../stores/wiki";

export default function ChatView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { chatMessages, addChatMessage, appendToLastChat, setLastChatReferences } = useWikiStore();
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  function handleSend() {
    if (!input.trim() || !id || streaming) return;
    const question = input.trim();
    setInput("");
    addChatMessage({ role: "user", content: question });
    addChatMessage({ role: "assistant", content: "" });
    setStreaming(true);

    let receivedContent = false;

    streamChat(
      id,
      question,
      (data) => {
        if (data.references) setLastChatReferences(data.references as ChatReference[]);
        if (typeof data.content === "string" && data.content) {
          receivedContent = true;
          appendToLastChat(data.content);
        }
        if (typeof data.error === "string" && data.error) {
          appendToLastChat(receivedContent ? `\n\n⚠️ ${data.error}` : data.error);
        }
      },
      () => setStreaming(false),
      (message) => {
        appendToLastChat(message);
        setStreaming(false);
      },
    );
  }

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(`/project/${id}`)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md text-xs font-medium transition-colors"
          >
            &larr; Back to Wiki
          </button>

          <span className="text-slate-300">|</span>

          <nav className="flex items-center gap-2 text-xs font-medium">
            <button onClick={() => navigate("/dashboard")} className="text-slate-500 hover:text-slate-900">
              Dashboard
            </button>
            <span className="text-slate-300">/</span>
            <button onClick={() => navigate("/repositories")} className="text-slate-500 hover:text-slate-900">
              Repositories
            </button>
            <span className="text-slate-300">/</span>
            <span className="text-blue-600 font-semibold">AI Assistant</span>
          </nav>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/dashboard")}
            className="px-3 py-1.5 border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-md text-xs font-medium transition-all"
          >
            Dashboard
          </button>
          <button
            onClick={() => navigate("/repositories")}
            className="px-3 py-1.5 border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-md text-xs font-medium transition-all"
          >
            Repositories
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {chatMessages.length === 0 && (
          <div className="text-center text-slate-500 mt-12 max-w-xl mx-auto space-y-6">
            <div className="w-12 h-12 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center mx-auto text-xl font-bold shadow-2xs">
              💬
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 mb-1">AI Codebase Assistant & Root Cause Diagnostic</h2>
              <p className="text-xs text-slate-500">Ask general Q&A questions or report feature errors to find the root cause & fix.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-left">
              <button
                onClick={() => setInput("This feature was working well but now it is not working showing this error: ")}
                className="p-3 bg-white border border-slate-200 hover:border-blue-400 rounded-lg text-xs transition-all shadow-2xs group"
              >
                <span className="font-semibold text-blue-600 block mb-0.5 group-hover:text-blue-700">🔍 Root Cause Analysis</span>
                <span className="text-slate-500">"This feature was working well but now showing error..."</span>
              </button>

              <button
                onClick={() => setInput("Find all dead code, unused imports, and unreferenced dependencies in this codebase.")}
                className="p-3 bg-white border border-slate-200 hover:border-amber-400 rounded-lg text-xs transition-all shadow-2xs group"
              >
                <span className="font-semibold text-amber-600 block mb-0.5 group-hover:text-amber-700">🧹 Dead Code Audit</span>
                <span className="text-slate-500">"Find all dead code and unused imports with reasons..."</span>
              </button>

              <button
                onClick={() => setInput("Check repository folder structure compliance against backend/frontend standards.")}
                className="p-3 bg-white border border-slate-200 hover:border-emerald-400 rounded-lg text-xs transition-all shadow-2xs group"
              >
                <span className="font-semibold text-emerald-600 block mb-0.5 group-hover:text-emerald-700">📁 Folder Structure Audit</span>
                <span className="text-slate-500">"Check if backend and frontend follow services layout..."</span>
              </button>

              <button
                onClick={() => setInput("Explain the authentication flow in src/app/services/auth/")}
                className="p-3 bg-white border border-slate-200 hover:border-purple-400 rounded-lg text-xs transition-all shadow-2xs group"
              >
                <span className="font-semibold text-purple-600 block mb-0.5 group-hover:text-purple-700">📖 Feature Q&A</span>
                <span className="text-slate-500">"Explain the authentication flow in service modules..."</span>
              </button>
            </div>
          </div>
        )}
        {chatMessages.map((msg, i) => (
          <div
            key={i}
            className={`max-w-3xl ${msg.role === "user" ? "ml-auto" : "mr-auto"}`}
          >
            <div
              className={`rounded-xl px-5 py-4 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white shadow-xs"
                  : "bg-white border border-slate-200 text-slate-800 shadow-xs"
              }`}
            >
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                {msg.content ||
                  (streaming && i === chatMessages.length - 1 && msg.role === "assistant"
                    ? "Analyzing codebase…"
                    : msg.role === "assistant"
                      ? "No response received. Check Settings → OpenRouter API key, then try again."
                      : "")}
              </pre>
              {msg.references && msg.references.length > 0 && (
                <div className="mt-4 pt-3 border-t border-slate-100 space-y-2">
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Inspected Feature & Action Sources</p>
                  {msg.references.map((ref, j) => (
                    <details key={j} className="group rounded-md border border-slate-200 bg-slate-50 overflow-hidden">
                      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-mono text-blue-700 hover:bg-slate-100 flex items-center justify-between font-semibold">
                        <span>📄 {ref.path}:{ref.line_start}-{ref.line_end}</span>
                        <span className="text-[12px] text-slate-400 group-open:rotate-180 transition-transform">▼</span>
                      </summary>
                      <pre className="p-3 text-xs font-mono text-slate-100 whitespace-pre-wrap border-t border-slate-800 bg-slate-900 overflow-x-auto">{ref.snippet}</pre>
                    </details>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="px-6 py-4 bg-white border-t border-slate-200">
        <div className="max-w-3xl mx-auto flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Report a feature issue/error (e.g. 'This feature was working well but now failing with error X')..."
            className="flex-1 px-4 py-2.5 rounded-lg border border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none text-sm text-slate-900"
            disabled={streaming}
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim()}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-xs"
          >
            {streaming ? "Analyzing..." : "Diagnose & Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
*/

export default function ChatView() {
  return <Navigate to="/investigation" replace />;
}
