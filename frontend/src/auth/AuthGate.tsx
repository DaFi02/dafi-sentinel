// AuthGate: redirects to /login when no session, blocks the route on
// 401/403 from the workbench server.

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useSession } from "./useAuth";

export function AuthGate({ children }: { children: ReactNode }) {
  const { session, hydrated } = useSession();
  const location = useLocation();

  if (!hydrated) {
    return <p className="muted">checking session…</p>;
  }
  if (!session) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
