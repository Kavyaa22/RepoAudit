import { Outlet } from "react-router-dom";
import { Sidebar } from "./sidebar";

export function AppShellLayout() {
  return (
    <div className="flex h-screen bg-[#F4F6FA] text-slate-800 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6 md:p-8 min-w-0">
        <div className="mx-auto w-full max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}




