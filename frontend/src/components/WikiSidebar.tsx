import type { SidebarItem } from "../lib/api";

interface Props {
  sidebar: SidebarItem[];
  currentPageId: string;
  projectName: string;
  onNavigate: (pageId: string) => void;
  onChat: () => void;
  onHome: () => void;
  onDashboard: () => void;
  onRepositories: () => void;
}

export default function WikiSidebar({
  sidebar,
  currentPageId,
  projectName,
  onNavigate,
  onDashboard,
  onRepositories,
  onHome,
  onChat,
}: Props) {
  const getBadge = (pageId: string) => {
    if (pageId === "structure-audit") return "Folders";
    if (pageId === "dead-code-audit") return "Cleanup";
    if (pageId === "security-audit") return "Security";
    if (pageId === "architecture" || pageId === "dependencies") return "Map";
    if (pageId.startsWith("modules/")) return "Domain";
    return null;
  };

  return (
    <aside className="w-max min-w-[16rem] max-w-[28rem] bg-slate-50 border-r border-slate-200 flex flex-col h-full shrink-0">
      <div className="p-3 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2 mb-2">
          <button
            onClick={onDashboard}
            className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-medium"
          >
            Dashboard
          </button>
          <button
            onClick={onRepositories}
            className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-medium"
          >
            Repos
          </button>
        </div>

        <div className="flex items-center gap-2 pt-1">
          <div className="w-7 h-7 rounded bg-blue-600 text-white flex items-center justify-center font-bold text-xs shrink-0">
            {projectName ? projectName.charAt(0).toUpperCase() : "R"}
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-xs font-bold text-slate-900 break-words" title={projectName}>
              {projectName || "Repository"}
            </h2>
            <span className="text-[12px] text-emerald-700 font-medium">Audit Complete</span>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-1">
        <div className="px-2 pb-1 text-[12px] font-bold text-slate-400 uppercase tracking-wider">
          Audit Report
        </div>

        {sidebar.map((item) => {
          const badge = item.page_id ? getBadge(item.page_id) : null;
          return (
            <div key={item.page_id || item.title}>
              {item.page_id ? (
                <button
                  onClick={() => onNavigate(item.page_id)}
                  className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded text-xs transition-colors ${
                    currentPageId === item.page_id
                      ? "bg-blue-600 text-white font-semibold"
                      : "text-slate-700 hover:bg-slate-200/60"
                  }`}
                >
                  <span className="text-left whitespace-normal break-words">{item.title}</span>
                  {badge && (
                    <span className={`text-[11px] px-1 py-0.5 rounded font-semibold shrink-0 ${
                      currentPageId === item.page_id ? "bg-white text-blue-700" : "bg-blue-100 text-blue-700"
                    }`}>
                      {badge}
                    </span>
                  )}
                </button>
              ) : (
                <div className="px-2 pt-2 pb-1 text-[12px] font-bold text-slate-400 uppercase tracking-wider border-t border-slate-200/60 mt-2">
                  {item.title}
                </div>
              )}
              {item.children?.map((child) => (
                <button
                  key={child.page_id}
                  onClick={() => onNavigate(child.page_id)}
                  className={`w-full text-left pl-6 pr-2.5 py-1 rounded text-xs transition-colors whitespace-normal break-words ${
                    currentPageId === child.page_id
                      ? "bg-blue-50 text-blue-700 font-semibold"
                      : "text-slate-600 hover:bg-slate-200/50"
                  }`}
                >
                  {child.title}
                </button>
              ))}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-slate-200 p-3 bg-white space-y-2">
        <button
          onClick={onChat}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-medium"
        >
          Issue Investigator
        </button>

        <button
          onClick={onHome}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 border border-slate-200 hover:bg-slate-50 text-slate-700 rounded text-xs font-medium"
        >
          New Audit
        </button>
      </div>
    </aside>
  );
}
