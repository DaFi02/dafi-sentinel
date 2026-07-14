// Session bootstrap. The provider hydrates the API client from
// localStorage, exposes the current session, and offers a logout helper
// that wipes the token everywhere it is cached.

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, type SessionResponse } from "../api/client";

type SessionContextValue = {
  session: SessionResponse | null;
  hydrated: boolean;
  login: (username: string, password: string) => Promise<SessionResponse>;
  logout: () => Promise<void>;
};

const STORAGE_KEY = "dafi-sentinel:session";

const SessionContext = createContext<SessionContextValue | undefined>(undefined);

function readStoredSession(): SessionResponse | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as SessionResponse;
    if (!parsed || typeof parsed.token !== "string") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function persistSession(session: SessionResponse | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (session) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    const stored = readStoredSession();
    if (stored) {
      apiClient.setToken(stored.token);
    }
    setSession(stored);
    setHydrated(true);
  }, []);

  const loginMutation = useMutation<SessionResponse, Error, { username: string; password: string }>({
    mutationFn: async (payload) => apiClient.login(payload.username, payload.password),
    onSuccess: (next) => {
      apiClient.setToken(next.token);
      persistSession(next);
      setSession(next);
      queryClient.setQueryData(["me"], next);
    },
  });

  const logoutMutation = useMutation<void, Error, string>({
    mutationFn: async (token) => {
      await apiClient.logout(token);
    },
    onSettled: () => {
      apiClient.setToken(null);
      persistSession(null);
      setSession(null);
      queryClient.setQueryData(["me"], null);
      queryClient.invalidateQueries();
    },
  });

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      hydrated,
      login: async (username, password) => loginMutation.mutateAsync({ username, password }),
      logout: async () => {
        if (session) {
          await logoutMutation.mutateAsync(session.token);
        } else {
          apiClient.setToken(null);
          persistSession(null);
          setSession(null);
          queryClient.invalidateQueries();
        }
      },
    }),
    [session, hydrated, loginMutation, logoutMutation, queryClient],
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

export function useMeProbe(enabled: boolean) {
  return useQuery<SessionResponse | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await apiClient.me();
      } catch {
        return null;
      }
    },
    enabled,
  });
}
