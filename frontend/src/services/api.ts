/**
 * Typed API client for the AegisHealth KBQA FastAPI backend.
 *
 * Rules:
 *  - All backend calls go through this module — never call fetch() directly
 *    in components.
 *  - Every request automatically attaches the Supabase Bearer token from the
 *    current session.
 *  - Error handling is centralised: throws ApiError with status + error_code.
 */

import { getAccessToken } from "./supabase";
import type {
  AdminMetricsResponse,
  ChatResponse,
  ConversationCreateRequest,
  ConversationDetail,
  ConversationSummary,
  CurrentUserResponse,
  DiseaseDetailResponse,
  DiseaseListResponse,
  ExportFormat,
  FeedbackCreateRequest,
  FeedbackResponse,
  HealthResponse,
  MessageCreateRequest,
  MessageTraceResponse,
  QueryRequest,
  QueryResponse,
  ReviewQueueResponse,
  StreamEvent,
  StreamEventType,
  UserPreferences,
  UserPreferencesResponse,
} from "../types/api";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

// ── Core HTTP helper ──────────────────────────────────────────────────────────

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** If false, skip attaching the Authorization header (e.g. health check). */
  authenticated?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, authenticated = true } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (authenticated) {
    const token = await getAccessToken();
    if (!token) {
      // Caller should handle navigation; throw a typed 401.
      const err = {
        message: "Session invalid or missing. Please sign in again.",
        error_code: "AUTHENTICATION_REQUIRED",
        status: 401,
      };
      throw err;
    }
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload?.detail ?? payload;
    const errorCode =
      typeof detail === "object" && detail !== null ? detail?.error_code : undefined;
    const message =
      (typeof detail === "object" && detail !== null ? detail?.message : undefined) ??
      detail?.answer ??
      `Request failed with status ${response.status}`;

    const err = {
      message,
      error_code: errorCode,
      detail,
      status: response.status,
    };

    // Surface specific error types so callers can react correctly.
    if (response.status === 401) {
      throw { ...err, error_code: err.error_code ?? "AUTHENTICATION_REQUIRED" };
    }
    if (response.status === 403) {
      throw { ...err, error_code: err.error_code ?? "FORBIDDEN" };
    }
    if (response.status === 404) {
      throw { ...err, error_code: err.error_code ?? "NOT_FOUND" };
    }

    throw err;
  }

  return payload as T;
}

async function authenticatedJsonHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  if (!token) {
    throw {
      message: "Session invalid or missing. Please sign in again.",
      error_code: "AUTHENTICATION_REQUIRED",
      status: 401,
    };
  }
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

function parseSseBlock(block: string): StreamEvent | null {
  let event: StreamEventType | null = null;
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim() as StreamEventType;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (!event || dataLines.length === 0) return null;
  return { event, data: JSON.parse(dataLines.join("\n")) } as StreamEvent;
}

async function throwResponseError(response: Response): Promise<never> {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail ?? payload;
  const errorCode =
    typeof detail === "object" && detail !== null ? detail?.error_code : undefined;
  const message =
    (typeof detail === "object" && detail !== null ? detail?.message : undefined) ??
    `Request failed with status ${response.status}`;
  throw { message, error_code: errorCode, detail, status: response.status };
}

// ── Public API functions ──────────────────────────────────────────────────────

/** GET /api/v1/health — unauthenticated */
export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/v1/health", { authenticated: false });
}

/** GET /api/v1/me — requires valid Supabase session */
export async function getMe(): Promise<CurrentUserResponse> {
  return request<CurrentUserResponse>("/api/v1/me");
}

/** GET /api/v1/conversations */
export async function listConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/api/v1/conversations");
}

/** POST /api/v1/conversations */
export async function createConversation(
  payload: ConversationCreateRequest
): Promise<ConversationSummary> {
  return request<ConversationSummary>("/api/v1/conversations", {
    method: "POST",
    body: payload,
  });
}

/** GET /api/v1/conversations/:id */
export async function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/v1/conversations/${id}`);
}

/** POST /api/v1/conversations/:id/messages */
export async function sendMessage(
  conversationId: string,
  payload: MessageCreateRequest
): Promise<ChatResponse> {
  return request<ChatResponse>(`/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    body: payload,
  });
}

interface SendMessageStreamOptions {
  onEvent?: (event: StreamEvent) => void;
}

/** POST /api/v1/conversations/:id/messages/stream — fetch-based SSE with auth */
export async function sendMessageStream(
  conversationId: string,
  payload: MessageCreateRequest,
  options: SendMessageStreamOptions = {},
): Promise<ChatResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/conversations/${conversationId}/messages/stream`,
    {
      method: "POST",
      headers: await authenticatedJsonHeaders(),
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    await throwResponseError(response);
  }
  if (!response.body) {
    throw {
      message: "Streaming response body is unavailable.",
      error_code: "STREAM_BODY_UNAVAILABLE",
      status: response.status,
    };
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: ChatResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (!event) continue;
      options.onEvent?.(event);
      if (event.event === "error") {
        throw {
          message: event.data.message,
          error_code: event.data.error_code,
          status: event.data.status_code ?? response.status,
        };
      }
      if (event.event === "final") {
        finalResponse = event.data;
      }
    }

    if (done) break;
  }

  if (!finalResponse) {
    throw {
      message: "Streaming ended before a final response was received.",
      error_code: "STREAM_FINAL_MISSING",
      status: response.status,
    };
  }
  return finalResponse;
}

/** GET /api/v1/conversations/:id/export?format=markdown|pdf */
export async function exportConversation(
  conversationId: string,
  format: ExportFormat,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/conversations/${conversationId}/export?format=${format}`,
    {
      method: "GET",
      headers: await authenticatedJsonHeaders(),
    },
  );

  if (!response.ok) {
    await throwResponseError(response);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const fallback = format === "pdf" ? "conversation.pdf" : "conversation.md";
  return {
    blob: await response.blob(),
    filename: match?.[1] ?? fallback,
  };
}

/** POST /api/v1/messages/:id/feedback */
export async function submitFeedback(
  messageId: string,
  payload: FeedbackCreateRequest
): Promise<FeedbackResponse> {
  return request<FeedbackResponse>(`/api/v1/messages/${messageId}/feedback`, {
    method: "POST",
    body: payload,
  });
}

// ── Legacy (existing /api/v1/query endpoint kept for backward compat) ─────────

/** POST /api/v1/query — legacy unauthenticated endpoint */
export async function queryMedical(payload: QueryRequest): Promise<QueryResponse> {
  return request<QueryResponse>("/api/v1/query", {
    method: "POST",
    body: payload,
    authenticated: false,
  });
}

// ── Knowledge ─────────────────────────────────────────────────────────────────

/** GET /api/v1/knowledge/diseases?q=&limit=&offset= — unauthenticated */
export async function listDiseases(
  q: string | null,
  limit = 20,
  offset = 0,
): Promise<DiseaseListResponse> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return request<DiseaseListResponse>(`/api/v1/knowledge/diseases?${params}`, {
    authenticated: false,
  });
}

/** GET /api/v1/knowledge/diseases/:id — unauthenticated */
export async function getDiseaseDetail(id: string): Promise<DiseaseDetailResponse> {
  return request<DiseaseDetailResponse>(
    `/api/v1/knowledge/diseases/${encodeURIComponent(id)}`,
    { authenticated: false },
  );
}

// ── Admin ─────────────────────────────────────────────────────────────────────

/** GET /api/v1/admin/metrics — requires admin role */
export async function getAdminMetrics(): Promise<AdminMetricsResponse> {
  return request<AdminMetricsResponse>("/api/v1/admin/metrics");
}

/** GET /api/v1/admin/review-items?limit=&offset= — requires admin role */
export async function getReviewQueue(
  limit = 20,
  offset = 0,
): Promise<ReviewQueueResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return request<ReviewQueueResponse>(`/api/v1/admin/review-items?${params}`);
}

// ── Sprint 1: Preferences ─────────────────────────────────────────────────────

/** GET /api/v1/me/preferences — requires authentication */
export async function getPreferences(): Promise<UserPreferencesResponse> {
  return request<UserPreferencesResponse>("/api/v1/me/preferences");
}

/** PATCH /api/v1/me/preferences — partial update */
export async function updatePreferences(
  patch: Partial<UserPreferences>,
): Promise<UserPreferencesResponse> {
  return request<UserPreferencesResponse>("/api/v1/me/preferences", {
    method: "PATCH",
    body: patch,
  });
}

// ── Sprint 1: Message trace ───────────────────────────────────────────────────

/** GET /api/v1/messages/:id/trace — owner / reviewer / admin */
export async function getMessageTrace(messageId: string): Promise<import("../types/api").MessageTraceResponse> {
  return request<import("../types/api").MessageTraceResponse>(
    `/api/v1/messages/${messageId}/trace`,
  );
}
