// Session bootstrap. The provider hydrates the API client from the
// HttpOnly session cookie (via a /sessions/me probe) and exposes the
// current user profile plus a logout helper. The cookie is set by the
// server on POST /sessions; the dashboard never reads or stores the
// token itself, so an XSS payload cannot exfiltrate it.
//
// The CRIT-1 fix removed the localStorage path entirely.

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, type SessionResponse } from "../api/client";

type SessionContextValue = {
  session: SessionResponse | null;
  hydrated: boolean;
  login: (username: string, password: string) => Promise<SessionResponse>;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | undefined>(undefined);

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  // The ``/sessions/me`` probe is the source of truth: if the cookie
  // is present and valid, the server returns the user profile. If the
  // cookie is absent or stale, the server returns 401 and the probe
  // resolves to ``null``. The dashboard never stores the token.
  const meQuery = useQuery<SessionResponse | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await apiClient.me();
      } catch {
        return null;
      }
    },
    // Re-probe on focus so a fresh tab picks up a new login on another
    // tab in the same browser.
    refetchOnWindowFocus: true,
  });

  const loginMutation = useMutation<SessionResponse, Error, { username: string; password: string }>({
    mutationFn: async (payload) => apiClient.login(payload.username, payload.password),
    onSuccess: (next) => {
      queryClient.setQueryData(["me"], next);
    },
  });

  const logoutMutation = useMutation<void, Error, void>({
    mutationFn: async () => {
      await apiClient.logout();
    },
    onSettled: () => {
      queryClient.setQueryData(["me"], null);
      queryClient.invalidateQueries();
    },
  });

  const session = meQuery.data ?? null;
  const hydrated = !meQuery.isLoading;

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      hydrated,
      login: async (username, password) => loginMutation.mutateAsync({ username, password }),
      logout: async () => {
        await logoutMutation.mutateAsync();
      },
    }),
    [session, hydrated, loginMutation, logoutMutation],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used inside a SessionProvider");
  }
  return ctx;
}
