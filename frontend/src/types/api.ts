export type QueryMode = "naive" | "local" | "global" | "hybrid" | "mix";
export type Language = "vi" | "en";
export type ResponseType = "text" | "table" | "warning";

export interface QueryRequest {
  question: string;
  language: Language;
  mode?: QueryMode;
}

export interface QueryMetadata {
  query_mode: string;
  execution_time_ms: number;
  source_count: number;
  engine: string;
  cypher?: string | null;
  error_code?: string | null;
  error_detail?: string | null;
}

export interface QueryResponse {
  status: "success" | "error";
  response_type: ResponseType | string;
  answer: string;
  data: Array<Record<string, unknown>> | null;
  metadata: QueryMetadata;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy" | string;
  services: {
    database: string;
    llm_server: string;
    embedding_server: string;
    lightrag: string;
    api: string;
  };
  version: string;
}

export interface ApiError {
  message: string;
  detail?: unknown;
  status?: number;
}
