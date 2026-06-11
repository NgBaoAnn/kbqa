/**
 * Typed contracts mirroring backend/app/models/contracts.py
 * Do not add response shapes that aren't in the backend contract.
 */

// ── Shared ────────────────────────────────────────────────────────────────────

export interface ApiError {
  message: string;
  error_code?: string;
  detail?: unknown;
  status?: number;
}

// ── Current User ──────────────────────────────────────────────────────────────

export interface CurrentUserResponse {
  id: string;
  email: string | null;
  role: "user" | "admin";
  display_name: string | null;
  is_active: boolean;
  auth_provider: "supabase";
}

// ── Conversations ─────────────────────────────────────────────────────────────

export interface ConversationCreateRequest {
  title?: string | null;
  language?: "vi" | "en";
}

export interface ConversationSummary {
  id: string;
  title: string;
  language: "vi" | "en";
  created_at: string;
  updated_at: string;
}

export interface MessageRecord {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  response_type?: string | null;
  data?: Record<string, unknown>[] | Record<string, unknown> | null;
  safety?: SafetyPayload | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ConversationDetail {
  conversation: ConversationSummary;
  messages: MessageRecord[];
}

// ── Messages / Chat ───────────────────────────────────────────────────────────

export interface MessageCreateRequest {
  question: string;
  mode?: string | null;
}

export interface ChatSource {
  id: string;
  source_type: string;
  title: string;
  snippet?: string | null;
  rank: number;
  metadata: Record<string, unknown>;
}

export interface SafetyPayload {
  level: "normal" | "caution" | "emergency";
  requires_emergency_notice: boolean;
  disclaimer: string;
}

export interface ChatMetadata {
  engine: string;
  query_mode: string;
  execution_time_ms: number;
  source_count: number;
  cypher?: string | null;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  status: "success" | "error";
  response_type: string;
  answer: string;
  data?: Record<string, unknown>[] | Record<string, unknown> | null;
  sources: ChatSource[];
  safety: SafetyPayload;
  suggested_questions: string[];
  metadata: ChatMetadata;
}

// ── Legacy (legacy /api/v1/query endpoint, kept for compat) ──────────────────

export type ResponseType = "text" | "table" | "warning";

export interface QueryRequest {
  question: string;
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
