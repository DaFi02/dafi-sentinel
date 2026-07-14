// AuthGate: redirects to /login when no session, blocks the route on
// 401/403 from the workbench server.

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useMeProbe } from "./useAuth";

export function AuthGate({ children }: { children: ReactNode }) {
  const probe = useMeProbe(true);
  const location = useLocation();

  if (probe.isLoading) {
    return <p className="muted">checking session…</p>;
  }
  if (!probe.data) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
