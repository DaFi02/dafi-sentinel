// TanStack Query hooks. The keys mirror the resource paths the workbench
// server exposes; the hooks are the only thing the pages import.
//
// The session bootstrap (me / login / logout) lives in
// ``src/auth/useAuth.tsx`` so the SessionProvider can own the cookie
// state in one place. The 4R review (R2 crit#4) flagged the duplicate
// useMe / useLogin / useLogout exports as dead code; the SessionProvider
// already implements the same shape inline, so the redundant exports
// are removed here.

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  type ChartResponse,
  type ChartSpecPayload,
  type EvidenceResponse,
  type QAResponse,
  type RoleResponse,
  type AuditsResponse,
  apiClient,
} from "./client";

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

export function useAskQuestion() {
  return useMutation<QAResponse, Error, { question: string; session_id: string; limit?: number }>({
    mutationFn: async (payload) => apiClient.askQuestion(payload),
  });
}

export function useRenderChart() {
  return useMutation<
    ChartResponse,
    Error,
    { spec: ChartSpecPayload; data: Array<[unknown, unknown]> }
  >({
    mutationFn: async (payload) => apiClient.renderChart(payload),
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
