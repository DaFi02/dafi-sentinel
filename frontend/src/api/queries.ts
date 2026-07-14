// TanStack Query hooks. The keys mirror the resource paths the workbench
// server exposes; the hooks are the only thing the pages import.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type ChartResponse,
  type ChartSpecPayload,
  type EvidenceResponse,
  type QAResponse,
  type RoleResponse,
  type SessionResponse,
  type AuditsResponse,
  apiClient,
} from "./client";

export function useMe(enabled: boolean) {
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

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<SessionResponse, Error, { username: string; password: string }>({
    mutationFn: async (payload) => apiClient.login(payload.username, payload.password),
    onSuccess: (session) => {
      apiClient.setToken(session.token);
      queryClient.setQueryData(["me"], session);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (token) => {
      await apiClient.logout(token);
    },
    onSuccess: () => {
      apiClient.setToken(null);
      queryClient.setQueryData(["me"], null);
      queryClient.invalidateQueries();
    },
  });
}

export function useEvidenceList(enabled: boolean) {
  return useQuery<EvidenceResponse[]>({
    queryKey: ["evidence"],
    queryFn: () => apiClient.listEvidence(),
    enabled,
  });
}

export function useEvidence(evidenceId: string | null, enabled: boolean) {
  return useQuery<EvidenceResponse>({
    queryKey: ["evidence", evidenceId],
    queryFn: () => apiClient.getEvidence(evidenceId as string),
    enabled: enabled && Boolean(evidenceId),
  });
}

export function useAskQuestion(enabled: boolean) {
  return useMutation<QAResponse, Error, { question: string; session_id: string; limit?: number }>({
    mutationFn: async (payload) => apiClient.askQuestion(payload),
    onSuccess: () => {
      // Refreshing audits is cheap and keeps the audit page fresh after Q&A.
      void enabled;
    },
  });
}

export function useRenderChart(enabled: boolean) {
  return useMutation<
    ChartResponse,
    Error,
    { spec: ChartSpecPayload; data: Array<[unknown, unknown]> }
  >({
    mutationFn: async (payload) => apiClient.renderChart(payload),
    onSuccess: () => {
      void enabled;
    },
  });
}

export function useRoles(userId: string | null, enabled: boolean) {
  return useQuery<RoleResponse>({
    queryKey: ["roles", userId],
    queryFn: () => apiClient.getRoles(userId as string),
    enabled: enabled && Boolean(userId),
  });
}

export function useAudits(enabled: boolean) {
  return useQuery<AuditsResponse>({
    queryKey: ["audits"],
    queryFn: () => apiClient.listAudits(),
    enabled,
  });
}
