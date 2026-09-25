import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "../../services/health";

export default function OverviewPage() {
  const [version, setVersion] = useState<string>("…");
  const [status, setStatus] = useState<string>("…");

  useEffect(() => {
    void getHealth()
      .then((h: HealthResponse) => {
        setVersion(h.version);
        setStatus(h.status);
      })
      .catch(() => {
        setStatus("unreachable");
        setVersion("—");
      });
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-800">Overview</h1>
      <p className="text-slate-600 text-sm">
        Backend status: <span className="text-slate-800">{status}</span> · v
        {version}
      </p>
      <p className="text-slate-500 text-sm max-w-xl">
        Feature modules are scaffolded under <code>src/app/*</code>. Legacy wiki
        scan UI remains at project routes.
      </p>
    </div>
  );
}
