import { Link } from "react-router-dom";
import { useAuth } from "../providers/auth-provider";

export function TopNavbar() {
  const { user } = useAuth();
  const userName = user?.full_name || "Kavya";
  const userInitial = userName ? userName[0].toUpperCase() : "K";

  return (
    <header className="flex h-14 items-center justify-end px-8 bg-[#F4F6FA] shrink-0">
      <Link
        to="/settings"
        className="flex items-center gap-2.5 px-3 py-1.5 rounded-full hover:bg-white/80 transition-all cursor-pointer"
        title="Account Settings"
      >
        <div className="w-8 h-8 rounded-full bg-[#DCE6FF] text-[#2563EB] font-bold text-xs flex items-center justify-center shrink-0">
          {userInitial}
        </div>
        <span className="text-xs font-semibold text-slate-800 flex items-center gap-1">
          {userName}
          <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </Link>
    </header>
  );
}



