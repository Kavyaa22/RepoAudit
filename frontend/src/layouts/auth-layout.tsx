import { Link, Outlet } from "react-router-dom";

export function AuthLayout() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col items-center justify-center p-4">
      {/* Brand Header */}
      <div className="mb-6 flex flex-col items-center text-center">
        <Link to="/" className="text-2xl font-bold text-slate-800">
          <span>
            <span className="text-blue-600">Repo</span>Audit
          </span>
        </Link>
        <p className="text-xs text-slate-500 mt-1">
          Code Intelligence & Static Structure Auditing
        </p>
      </div>

      {/* Auth Content Card */}
      <div className="w-full max-w-md">
        <Outlet />
      </div>

      <footer className="mt-8 text-center text-xs text-slate-400">
        © 2026 RepoAudit
      </footer>
    </div>
  );
}


