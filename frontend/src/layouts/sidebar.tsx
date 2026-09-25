import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../providers/auth-provider";

interface NavItem {
  label: string;
  path: string;
  icon: (active: boolean) => React.ReactNode;
}

const navItems: NavItem[] = [
  {
    label: "Dashboard",
    path: "/dashboard",
    icon: (active) => (
      <svg className={`w-5 h-5 ${active ? "text-[#2563EB]" : "text-slate-400"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 00-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    label: "Repositories",
    path: "/repositories",
    icon: (active) => (
      <svg className={`w-5 h-5 ${active ? "text-[#2563EB]" : "text-slate-400"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
      </svg>
    ),
  },
  {
    label: "Audit",
    path: "/audit",
    icon: (active) => (
      <svg className={`w-5 h-5 ${active ? "text-[#2563EB]" : "text-slate-400"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  },
  {
    label: "Issue Investigator",
    path: "/investigation",
    icon: (active) => (
      <svg className={`w-5 h-5 ${active ? "text-[#2563EB]" : "text-slate-400"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    ),
  },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const userName = user?.full_name || "Kavya";
  const userInitial = userName ? userName[0].toUpperCase() : "K";

  const handleLogout = async () => {
    await logout();
    navigate("/auth/login", { replace: true });
  };

  return (
    <aside className="w-max min-w-[14rem] max-w-[18rem] shrink-0 border-r border-slate-200 bg-white p-5 flex flex-col justify-between h-full z-10">
      <div className="space-y-6">
        {/* Brand Text Header (Icon Removed) */}
        <div className="px-2 pt-1">
          <span className="text-xl font-extrabold text-slate-900 tracking-tight">
            Repo<span className="text-[#2563EB]">Audit</span>
          </span>
        </div>

        {/* Main Navigation Links (Increased Font Size) */}
        <nav className="space-y-1.5">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                [
                  "flex items-center gap-3 px-3.5 py-3 rounded-xl text-sm font-semibold transition-all",
                  isActive
                    ? "bg-[#EEF2FF] text-[#2563EB] font-bold"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                ].join(" ")
              }
            >
              {({ isActive }) => (
                <>
                  {item.icon(isActive)}
                  <span>{item.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="space-y-3 pt-4 border-t border-slate-100">
        {/* User Profile Avatar & Name Chip (Above Logout) */}
        <div
          onClick={() => navigate("/settings")}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-slate-50 transition-all cursor-pointer border border-transparent hover:border-slate-200"
          title="Account Settings"
        >
          <div className="w-8 h-8 rounded-full bg-[#DCE6FF] text-[#2563EB] font-bold text-xs flex items-center justify-center shrink-0">
            {userInitial}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-bold text-slate-900 truncate">{userName}</div>
            <div className="text-[12px] text-slate-400 font-medium truncate">{user?.email || "Account Settings"}</div>
          </div>
          <svg className="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
          </svg>
        </div>

        {/* Logout Button */}
        <button
          type="button"
          onClick={() => void handleLogout()}
          className="w-full flex items-center gap-3 px-3 py-2.5 text-xs font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-50 rounded-xl transition-all cursor-pointer"
        >
          <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Logout
        </button>
      </div>
    </aside>
  );
}





