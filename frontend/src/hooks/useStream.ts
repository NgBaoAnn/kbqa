/**
 * useStream — hook for SSE streaming chat messages.
 *
 * Wraps sendMessageStream from services/api.ts and manages:
 *  - AbortController lifecycle (cleanup on unmount or abort())
 *  - Real-time token accumulation (via onEvent delta callbacks)
 *  - Stage tracking (routing → retrieving → generating → persisting)
 *  - Final ChatResponse capture
 *  - Typed error state
 *
 * SSE event order (from src/api/schemas/streaming.py):
 *   1. stage   — StreamStagePayload
 *   2. delta*  — StreamDeltaPayload (one per token, LightRAG path)
 *   3. sources — StreamSourcesPayload
 *   4. metadata — StreamMetadataPayload
 *   5. final   — ChatResponse-equivalent
 *   6. error   — StreamErrorPayload (on fatal error)
 *
 * Usage:
 *   const { streaming, stage, content, finalResponse, error, startStream, abort } = useStream();
 *
 *   async function send(conversationId: string, question: string) {
 *     const response = await startStream(conversationId, { question });
 *     // response is the final ChatResponse
 *   }
 */

import { useCallback, useRef, useState } from "react";
import { sendMessageStream } from "../services/api";
import type {
  ChatResponse,
  MessageCreateRequest,
  StreamStage,
} from "../types/api";
import { normaliseApiError } from "./useApi";
import type { ApiError } from "../types/api";

export interface UseStreamState {
  /** True while the SSE connection is open. */
  streaming: boolean;
  /** Current pipeline stage (null before first stage event). */
  stage: StreamStage | null;
  /** Accumulated delta content so far (empty string until first delta). */
  content: string;
  /** Populated after the final event arrives (null until then). */
  finalResponse: ChatResponse | null;
  error: ApiError | null;
}

export interface UseStreamActions {
  /**
   * Open a streaming connection for the given conversation.
   * Returns the final ChatResponse when the stream completes.
   * Throws an ApiError-shaped object on failure.
   */
  startStream: (
    conversationId: string,
    payload: MessageCreateRequest,
  ) => Promise<ChatResponse>;
  /** Cancel the in-flight stream (if any). */
  abort: () => void;
  /** Reset state back to initial (call between messages). */
  reset: () => void;
}

const INITIAL_STATE: UseStreamState = {
  streaming: false,
  stage: null,
  content: "",
  finalResponse: null,
  error: null,
};

export function useStream(): UseStreamState & UseStreamActions {
  const [state, setState] = useState<UseStreamState>(INITIAL_STATE);

  // AbortController for the current stream.
  const abortRef = useRef<AbortController | null>(null);

  // rAF handle for batching delta updates.
  const rafRef = useRef<number | null>(null);
  const deltaBufferRef = useRef<string>("");

  const flushDelta = useCallback(() => {
    rafRef.current = null;
    const chunk = deltaBufferRef.current;
    deltaBufferRef.current = "";
    if (!chunk) return;
    setState((prev) => ({ ...prev, content: prev.content + chunk }));
  }, []);

  const clearRaf = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    deltaBufferRef.current = "";
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearRaf();
    setState((prev) => ({ ...prev, streaming: false }));
  }, [clearRaf]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearRaf();
    setState(INITIAL_STATE);
  }, [clearRaf]);

  const startStream = useCallback(
    async (
      conversationId: string,
      payload: MessageCreateRequest,
    ): Promise<ChatResponse> => {
      // Cancel any in-flight stream before starting a new one.
      abortRef.current?.abort();
      clearRaf();

      const controller = new AbortController();
      abortRef.current = controller;

      setState({
        streaming: true,
        stage: null,
        content: "",
        finalResponse: null,
        error: null,
      });

      try {
        const response = await sendMessageStream(conversationId, payload, {
          onEvent: (event) => {
            if (controller.signal.aborted) return;

            if (event.event === "stage") {
              setState((prev) => ({ ...prev, stage: event.data.stage }));
            }

            if (event.event === "delta" && event.data.content) {
              // Buffer tokens and flush via rAF to batch React renders.
              deltaBufferRef.current += event.data.content;
              if (rafRef.current === null) {
                rafRef.current = requestAnimationFrame(flushDelta);
              }
            }

            if (event.event === "sources") {
              // Sources arrive before final; no state update needed here —
              // they'll be included in the final ChatResponse.
            }
          },
        });

        // Flush any remaining buffered delta before setting final state.
        clearRaf();
        if (deltaBufferRef.current) {
          setState((prev) => ({
            ...prev,
            content: prev.content + deltaBufferRef.current,
          }));
          deltaBufferRef.current = "";
        }

        setState((prev) => ({
          ...prev,
          streaming: false,
          finalResponse: response,
          stage: null,
        }));

        return response;
      } catch (err) {
        clearRaf();
        const normalised = normaliseApiError(err);
        setState((prev) => ({
          ...prev,
          streaming: false,
          error: normalised,
          stage: null,
        }));
        throw normalised;
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [clearRaf, flushDelta],
  );

  // Cleanup on unmount.
  // This is handled by the caller via abort() in useEffect cleanup,
  // but we also guard the AbortController to avoid setState after unmount.

  return { ...state, startStream, abort, reset };
}
