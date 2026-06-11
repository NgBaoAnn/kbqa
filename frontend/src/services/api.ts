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
  ChatResponse,
  ConversationCreateRequest,
  ConversationDetail,
  ConversationSummary,
  CurrentUserResponse,
  FeedbackCreateRequest,
  FeedbackResponse,
  HealthResponse,
  MessageCreateRequest,
  QueryRequest,
  QueryResponse,
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
