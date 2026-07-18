import type { ApiError, AskResponse, InvestigationContext, RetrievalHealth, RootStatus, Stats } from "./types";

export const DEFAULT_API_URL = process.env.NEXT_PUBLIC_FORGE_API_URL || "/forge-api";

function cleanBaseUrl(baseUrl: string) {
  return baseUrl.trim().replace(/\/+$/, "");
}

async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${cleanBaseUrl(baseUrl)}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new Error("Forge backend is unavailable. Check the API URL and make sure FastAPI is running.");
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(body.error?.message || body.detail || `Forge API returned ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export const forgeApi = {
  root: (baseUrl: string) => request<RootStatus>(baseUrl, "/"),
  health: (baseUrl: string) => request<RetrievalHealth>(baseUrl, "/health/retrieval", { method: "POST" }),
  stats: (baseUrl: string) => request<Stats>(baseUrl, "/stats"),
  ask: (baseUrl: string, question: string, maxEvidence = 5, investigationContext?: InvestigationContext) =>
    request<AskResponse>(baseUrl, "/ask", {
      method: "POST",
      body: JSON.stringify({ question, max_evidence: maxEvidence, investigation_context: investigationContext }),
    }),
};
