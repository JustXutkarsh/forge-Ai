"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { forgeApi } from "@/lib/api";
import type { InvestigationContext } from "@/lib/types";
import { useApiUrl } from "@/components/api-url-provider";

export function useForgeStatus() {
  const { apiUrl } = useApiUrl();
  return useQuery({ queryKey: ["forge-status", apiUrl], queryFn: () => forgeApi.root(apiUrl), refetchInterval: 20_000 });
}

export function useRetrievalHealth() {
  const { apiUrl } = useApiUrl();
  return useQuery({ queryKey: ["retrieval-health", apiUrl], queryFn: () => forgeApi.health(apiUrl), refetchInterval: 30_000 });
}

export function useForgeStats() {
  const { apiUrl } = useApiUrl();
  return useQuery({ queryKey: ["forge-stats", apiUrl], queryFn: () => forgeApi.stats(apiUrl), refetchInterval: 30_000 });
}

export function useAsk() {
  const { apiUrl } = useApiUrl();
  return useMutation({ mutationFn: ({ question, maxEvidence, investigationContext }: { question: string; maxEvidence?: number; investigationContext?: InvestigationContext }) => forgeApi.ask(apiUrl, question, maxEvidence, investigationContext) });
}
