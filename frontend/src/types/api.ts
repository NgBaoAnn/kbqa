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
  role: "user" | "reviewer" | "admin";
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
  sources?: ChatSource[];
  safety?: SafetyPayload | null;
  metadata: Record<string, unknown>;
  feedback?: { rating: "up" | "down"; reason?: string | null } | null;
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
  prompt_version?: string | null;
  model_name?: string | null;
  kg_version?: string | null;
  pipeline_version?: string | null;
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
  feedback?: { rating: "up" | "down"; reason?: string | null } | null;
}

// ── Feedback ──────────────────────────────────────────────────────────────────

export type FeedbackRating = "up" | "down";

export type FeedbackReason =
  | "helpful"
  | "incorrect"
  | "unsafe"
  | "unclear"
  | "incomplete"
  | "other";

export interface FeedbackCreateRequest {
  rating: FeedbackRating;
  reason?: FeedbackReason | null;
  comment?: string | null;
}

export interface FeedbackResponse {
  id: string;
  message_id: string;
  rating: string;
  reason: string | null;
  review_item_id: string | null;
  created_at: string;
}

export type ChatSourceType =
  | "cypher"
  | "neo4j"
  | "lightrag_entity"
  | "lightrag_relationship"
  | "lightrag_chunk"
  | "document"
  | "other";

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

// ── Knowledge ─────────────────────────────────────────────────────────────────

export interface DiseaseSummary {
  id: string;
  disease_name: string;
  disease_category: string | null;
  summary: string | null;
}

export interface DiseaseListResponse {
  items: DiseaseSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface DiseaseDetailResponse {
  id: string;
  disease_name: string;
  description: string | null;
  symptoms: string[];
  treatments: string[];
  medicines: string[];
  advice: string[];
  metadata: Record<string, unknown>;
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export interface AdminMetricsResponse {
  request_count: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  negative_feedback_rate: number;
  engine_usage: Record<string, number>;
  pending_review_count: number;
}

export interface ReviewItemRecord {
  id: string;
  status: "pending" | "resolved" | "dismissed";
  category: string;
  feedback_id: string;
  message_id: string;
  conversation_id: string;
  rating: string;
  reason: string | null;
  comment: string | null;
  created_at: string;
  question_content: string | null;
  answer_content: string | null;
}

export interface ReviewQueueResponse {
  items: ReviewItemRecord[];
  total: number;
  limit: number;
  offset: number;
}

// ── Sprint 1: Versioning + Preferences ────────────────────────────────

export interface VersionMetadata {
  prompt_version: string;
  model_name: string;
  kg_version: string;
  pipeline_version: string;
}

export interface UserPreferences {
  language: "vi" | "en";
  explanation_level: "general" | "detailed" | "expert";
  answer_style: "concise" | "detailed";
}

export interface UserPreferencesResponse extends UserPreferences {
  id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
}

export interface MessageTraceResponse {
  message_id: string;
  version_metadata: VersionMetadata;
  engine_metadata: Record<string, unknown>;
}
