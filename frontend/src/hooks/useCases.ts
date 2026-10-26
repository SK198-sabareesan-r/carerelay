import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type DateRange } from "../lib/api";
import type { CaseStatus } from "../types/case";

const POLL_INTERVAL_MS = 5000;

export function useCases(range?: DateRange) {
  return useQuery({
    queryKey: ["cases", range?.from ?? null, range?.to ?? null],
    queryFn: () => api.listCases(range),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useCase(caseId: string | undefined) {
  return useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.getCase(caseId as string),
    enabled: !!caseId,
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function usePayerRules() {
  return useQuery({
    queryKey: ["payer-rules"],
    queryFn: api.listPayerRules,
    staleTime: 60_000,
  });
}

export function useStats(range?: DateRange) {
  return useQuery({
    queryKey: ["stats", range?.from ?? null, range?.to ?? null],
    queryFn: () => api.getStats(range),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useCreateCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createCase,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cases"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useStartFollowup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.startFollowup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cases"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useUpdateCaseStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { caseId: string; status: CaseStatus; actor?: string; note?: string }) =>
      api.updateCaseStatus(input.caseId, input),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["cases"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      queryClient.invalidateQueries({ queryKey: ["case", variables.caseId] });
    },
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { caseId: string; text: string; actor?: string }) =>
      api.sendMessage(input.caseId, input),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["case", variables.caseId] });
    },
  });
}

export function useCreatePayerRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createPayerRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payer-rules"] });
    },
  });
}
