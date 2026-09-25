import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getWiki, getPage } from "../lib/api";
import { cacheGet } from "../lib/client-cache";
import { clearWikiCachesForIds } from "../lib/audit-history";
import { useWikiStore } from "../stores/wiki";
import WikiSidebar from "../components/WikiSidebar";
import WikiContent from "../components/WikiContent";
import DeadCodePromptPanel from "../components/DeadCodePromptPanel";
import { WikiPageSkeleton, Skeleton } from "../components/Skeleton";
import type { WikiPage, WikiStructure } from "../lib/api";

export default function WikiView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { wiki, setWiki, currentPageId, setCurrentPage, projectId, setProjectId } = useWikiStore();
  const mainRef = useRef<HTMLElement | null>(null);
  const cachedWiki = id ? cacheGet<WikiStructure>(`wiki:${id}`) : null;
  const activeWiki = wiki && projectId === id ? wiki : cachedWiki;
  const cachedPage = id && currentPageId ? cacheGet<WikiPage>(`wiki-page:${id}:${currentPageId}`) : null;
  const [pageContent, setPageContent] = useState(cachedPage?.content || "");
  const [pageTitle, setPageTitle] = useState(cachedPage?.title || "");
  const [loading, setLoading] = useState(!cachedPage);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (mainRef.current) {
      mainRef.current.scrollTo({ top: 0, left: 0, behavior: "instant" });
    }
  }, [currentPageId, pageContent]);

  useEffect(() => {
    if (!id) return;
    setLoadError(null);
    if (projectId !== id && cachedWiki) {
      setWiki(cachedWiki);
      setProjectId(id);
    }
    getWiki(id)
      .then((w) => {
        if ("error" in w) {
          clearWikiCachesForIds([id]);
          setLoadError(typeof w.error === "string" ? w.error : "Could not load audit report");
          return;
        }
        setWiki(w);
        setProjectId(id);
        const pageIds = (w.pages || []).map((p) => p.id);
        if (pageIds.length > 0 && !pageIds.includes(currentPageId)) {
          setCurrentPage(w.pages[0].id);
        }
      })
      .catch((err) => {
        if (!cachedWiki && !(wiki && projectId === id)) {
          setLoadError(err instanceof Error ? err.message : "Failed to load audit report");
        }
      });
  }, [id, setWiki, setCurrentPage, setProjectId]);

  useEffect(() => {
    if (!id || !currentPageId) return;
    const cachedPage = cacheGet<WikiPage>(`wiki-page:${id}:${currentPageId}`);
    if (cachedPage && !("error" in cachedPage)) {
      setPageContent(cachedPage.content);
      setPageTitle(cachedPage.title);
      setLoading(false);
    } else {
      setLoading(true);
    }
    getPage(id, currentPageId).then((p) => {
      if ("error" in p) {
        if (!cachedPage) {
          setPageContent("Page content not found.");
          setPageTitle("Error");
        }
      } else {
        setPageContent(p.content);
        setPageTitle(p.title);
      }
      setLoading(false);
    });
  }, [id, currentPageId]);

  if (loadError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-700 p-4">
        <div className="flex flex-col items-center gap-4 max-w-md text-center p-6 bg-white rounded-lg border border-slate-200">
          <h2 className="text-base font-bold text-slate-900">Audit Report Notice</h2>
          <p className="text-xs text-slate-500">{loadError}</p>
          <Link
            to="/audit"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg"
          >
            &larr; Back to Audits
          </Link>
        </div>
      </div>
    );
  }

  if (!activeWiki) {
    return <WikiPageSkeleton />;
  }

  return (
    <div className="flex flex-col h-screen bg-slate-50 overflow-hidden">
      <header className="h-14 border-b border-slate-200 bg-white px-6 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <Link
            to="/dashboard"
            className="text-base font-bold text-slate-800 flex items-center gap-2"
          >
            <span>
              <span className="text-blue-600">Repo</span>Audit
            </span>
          </Link>

          <span className="text-slate-300">/</span>

          <nav className="flex items-center gap-2 text-xs font-medium">
            <Link to="/dashboard" className="text-slate-500 hover:text-slate-900">
              Dashboard
            </Link>
            <span className="text-slate-300">/</span>
            <span className="text-slate-800 font-semibold">{activeWiki.project_name || "Repository"}</span>
          </nav>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/audit")}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium"
          >
            New Audit
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <WikiSidebar
          sidebar={activeWiki.sidebar}
          currentPageId={currentPageId}
          projectName={activeWiki.project_name}
          onNavigate={(pageId) => setCurrentPage(pageId)}
          onChat={() => navigate("/investigation")}
          onDashboard={() => navigate("/dashboard")}
          onRepositories={() => navigate("/repositories")}
          onHome={() => navigate("/audit")}
        />

        <main ref={mainRef} className="flex-1 overflow-y-auto bg-white min-w-0">
          {loading && !pageContent ? (
            <div className="px-6 py-8 space-y-4">
              <Skeleton className="h-8 w-72" />
              <Skeleton className="h-4 w-full max-w-2xl" />
              <Skeleton className="h-4 w-5/6" />
              <div className="pt-4 space-y-2">
                <Skeleton className="h-10 w-full" />
                {Array.from({ length: 8 }).map((_, idx) => (
                  <Skeleton key={idx} className="h-12 w-full" />
                ))}
              </div>
            </div>
          ) : (
            <>
              {currentPageId === "dead-code-audit" && id && (
                <div className="px-6 pt-6">
                  <DeadCodePromptPanel projectId={id} />
                </div>
              )}
              <WikiContent
                content={pageContent}
                title={pageTitle}
                onNavigate={(pageId) => setCurrentPage(pageId)}
              />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
