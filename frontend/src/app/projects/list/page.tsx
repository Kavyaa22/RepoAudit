import { useEffect, useState } from "react";
import { apiClient } from "../../../services/api-client";

type ProjectSummary = {
  project_id: string;
  display_name: string;
  repository_url: string;
  status: string;
};

export default function ProjectsListPage() {
  const [items, setItems] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const { data } = await apiClient.get<{
          success: boolean;
          data: { items: ProjectSummary[] };
        }>("/projects");
        setItems(data.data.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load projects");
      }
    })();
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-800">Projects</h1>
      {error && <p className="text-red-500 text-sm">{error}</p>}
      {items.length === 0 && !error ? (
        <p className="text-slate-500 text-sm">No projects yet.</p>
      ) : (
        <ul className="divide-y divide-slate-200 border border-slate-200 rounded-lg bg-white">
          {items.map((p) => (
            <li key={p.project_id} className="px-4 py-3">
              <div className="font-medium text-slate-800">{p.display_name}</div>
              <div className="text-xs text-slate-500">{p.repository_url}</div>
              <div className="text-xs text-slate-500 mt-1">{p.status}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
