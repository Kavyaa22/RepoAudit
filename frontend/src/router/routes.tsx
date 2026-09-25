import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../providers/auth-provider";
import { AuthLayout } from "../layouts/auth-layout";
import { AppShellLayout } from "../layouts/app-shell-layout";
import { RequireAuth } from "../components/common/RequireAuth";
import LoginPage from "../app/auth/login/page";
import DashboardPage from "../app/dashboard/page";
import ProjectsListPage from "../app/projects/list/page";
import RepositoriesPage from "../app/repositories/list/page";
import AuditPage from "../app/audit/list/page";
// import PlaceholderPage from "../app/_shared/PlaceholderPage";
import { env } from "../config/env";
import { useAuth } from "../providers/auth-provider";

// import AIChatPage from "../app/ai/chat/AIChatPage";

import InvestigationPage from "../app/investigation/page";
import SettingsPage from "../app/settings/page";

// Legacy wiki result views (opened after audit completes)
import WikiView from "../pages/WikiView";
// import ChatView from "../pages/ChatView";

function RootRedirect() {
  const { isAuthenticated } = useAuth();
  if (env.authDisabled || isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Navigate to="/auth/login" replace />;
}

export function AppRoutes() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/project/:id" element={<WikiView />} />
          {/* AI chat disabled — Issue Investigator is the primary workflow */}
          {/* <Route path="/project/:id/chat" element={<ChatView />} /> */}
          <Route path="/project/:id/chat" element={<Navigate to="/investigation" replace />} />

          <Route element={<AuthLayout />}>
            <Route path="/auth/login" element={<LoginPage />} />
            <Route path="/auth/logout" element={<Navigate to="/auth/login" replace />} />
          </Route>

          <Route
            element={
              <RequireAuth>
                <AppShellLayout />
              </RequireAuth>
            }
          >
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/overview" element={<Navigate to="/dashboard" replace />} />
            <Route path="/projects" element={<Navigate to="/repositories" replace />} />
            <Route path="/repositories" element={<RepositoriesPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/investigation" element={<InvestigationPage />} />
            {/* <Route path="/knowledge" element={<PlaceholderPage title="Knowledge" />} /> */}
            {/* <Route path="/ai/chat" element={<AIChatPage />} /> */}
            <Route path="/ai/chat" element={<Navigate to="/investigation" replace />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
