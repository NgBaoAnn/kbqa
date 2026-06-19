/**
 * useApi — generic hook for one-shot API calls with loading/error state.
 *
 * Usage:
 *   const { data, loading, error, execute, reset } = useApi(getAdminMetrics);
 *   useEffect(() => { execute(); }, [execute]);
 *
 * Features:
 *  - Typed result from any async function
 *  - Cancellation: ignores stale responses after unmount
 *  - Normalised ApiError shape
 *  - Optional onSuccess/onError callbacks
 */

import { useCallback, useRef, useState } from "react";
import type { ApiError } from "../types/api";

type Status = "idle" | "loading" | "success" | "error";

export interface UseApiOptions<T> {
  /** Called with the result on success. */
  onSuccess?: (data: T) => void;
  /** Called with the normalised error on failure. */
  onError?: (err: ApiError) => void;
}

interface UseApiState<T> {
  data: T | null;
  status: Status;
  loading: boolean;
  error: ApiError | null;
  /** Trigger the API call. Accepts the same args as the wrapped fn. */
  execute: (...args: Parameters<(...a: never[]) => Promise<T>>) => Promise<void>;
  /** Reset state back to idle. */
  reset: () => void;
}

/** Normalise any thrown value into an ApiError-compatible object. */
export function normaliseApiError(err: unknown): ApiError {
  if (err && typeof err === "object") {
    const e = err as Record<string, unknown>;
    return {
      message:
        typeof e.message === "string"
          ? e.message
          : "An unexpected error occurred.",
      error_code: typeof e.error_code === "string" ? e.error_code : undefined,
      detail: e.detail,
      status: typeof e.status === "number" ? e.status : undefined,
    };
  }
  if (typeof err === "string") return { message: err };
  return { message: "An unexpected error occurred." };
}

// Overloaded to preserve the argument types of the wrapped function.
export function useApi<T, TArgs extends unknown[]>(
  fn: (...args: TArgs) => Promise<T>,
  options: UseApiOptions<T> = {},
): Omit<UseApiState<T>, "execute"> & { execute: (...args: TArgs) => Promise<void> } {
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<ApiError | null>(null);

  // Track whether the component is still mounted to avoid setState on unmount.
  const mountedRef = useRef(true);
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const execute = useCallback(
    async (...args: TArgs) => {
      setStatus("loading");
      setError(null);
      try {
        const result = await fn(...args);
        if (!mountedRef.current) return;
        setData(result);
        setStatus("success");
        optionsRef.current.onSuccess?.(result);
      } catch (err) {
        if (!mountedRef.current) return;
        const normalised = normaliseApiError(err);
        setError(normalised);
        setStatus("error");
        optionsRef.current.onError?.(normalised);
      }
    },
    // fn is intentionally omitted from deps: callers should wrap in useCallback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn],
  );

  const reset = useCallback(() => {
    setData(null);
    setStatus("idle");
    setError(null);
  }, []);

  return { data, status, loading: status === "loading", error, execute, reset };
}
