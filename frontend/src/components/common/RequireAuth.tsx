import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { env } from "../../config/env";
import { useAuth } from "../../providers/auth-provider";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (env.authDisabled) return <>{children}</>;
  if (!isAuthenticated) {
    return <Navigate to="/auth/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
