import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

const POLL_INTERVAL_MS = 5000;

export function useCases() {
  return useQuery({
    queryKey: ["cases"],
    queryFn: api.listCases,
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

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: api.getStats,
    refetchInterval: POLL_INTERVAL_MS,
  });
}
