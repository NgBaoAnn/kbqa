import type { HealthResponse, QueryRequest, QueryResponse } from "../types/api";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload?.detail ?? payload;
    const message =
      detail?.answer ??
      detail?.metadata?.error_detail ??
      `Request failed with status ${response.status}`;

    throw {
      message,
      detail,
      status: response.status,
    };
  }

  return payload as T;
}

export async function queryMedical(request: QueryRequest): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  return parseJson<QueryResponse>(response);
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`);
  return parseJson<HealthResponse>(response);
}
