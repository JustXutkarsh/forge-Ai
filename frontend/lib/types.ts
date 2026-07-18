export type RootStatus = {
  status: string;
  version: string;
  embedding_provider: string;
  embedding_model: string;
  llm_provider: string;
  semantic_ready: boolean;
};

export type EvidenceItem = {
  ticket_id: string;
  score: number;
  summary: string;
};

export type Timings = {
  embedding_ms: number;
  retrieval_ms: number;
  reasoning_ms: number;
  total_ms: number;
};

export type AskResponse = {
  question: string;
  answer: string;
  confidence: number;
  retrieval_strategy: string;
  reasoning_provider: string;
  evidence: EvidenceItem[];
  timings: Timings;
};

export type InvestigationContext = {
  retrieval_strategy: string;
  evidence: EvidenceItem[];
};

export type RetrievalHealth = {
  status: string;
  chroma_reachable: boolean;
  sqlite_reachable: boolean;
  embedding_model_loaded: boolean;
  collection_size: number | null;
  latency_ms: number;
};

export type Stats = {
  total_tickets: number;
  embedded_tickets: number;
  embedding_model: string;
  vector_dimension: number | null;
  chroma_collection_count: number | null;
};

export type ApiError = {
  error?: { code?: string; message?: string };
  detail?: string;
};
