/**
 * useConversations — manages the conversation list in the Zustand store.
 *
 * Responsibilities:
 *  - Fetch conversation list from backend on mount (or on explicit refresh)
 *  - Expose createConversation that optimistically adds the new item
 *  - Sync results into the global store so sidebar re-renders automatically
 *
 * Usage:
 *   const {
 *     conversations, loading, error,
 *     refresh, createConversation,
 *     activeConversationId, setActive,
 *   } = useConversations();
 */

import { useCallback, useEffect } from "react";
import {
  createConversation as apiCreateConversation,
  listConversations as apiListConversations,
} from "../services/api";
import type { ConversationCreateRequest, ConversationSummary } from "../types/api";
import {
  selectActiveConversationId,
  selectConversations,
  useAppStore,
} from "../app/store";
import { normaliseApiError } from "./useApi";

const LOAD_KEY = "conversations:list";
const CREATE_KEY = "conversations:create";

export function useConversations() {
  const conversations = useAppStore(selectConversations);
  const activeConversationId = useAppStore(selectActiveConversationId);
  const {
    setConversations,
    addConversation,
    setActiveConversationId,
    setLoading,
    setError,
    loading,
    errors,
  } = useAppStore();

  const isLoading = loading[LOAD_KEY] ?? false;
  const isCreating = loading[CREATE_KEY] ?? false;
  const listError = errors[LOAD_KEY] ?? null;
  const createError = errors[CREATE_KEY] ?? null;

  const refresh = useCallback(async () => {
    setLoading(LOAD_KEY, true);
    setError(LOAD_KEY, null);
    try {
      const list = await apiListConversations();
      setConversations(list);
    } catch (err) {
      setError(LOAD_KEY, normaliseApiError(err).message);
    } finally {
      setLoading(LOAD_KEY, false);
    }
  }, [setConversations, setLoading, setError]);

  // Load on mount.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createConversation = useCallback(
    async (
      payload: ConversationCreateRequest = {},
    ): Promise<ConversationSummary> => {
      setLoading(CREATE_KEY, true);
      setError(CREATE_KEY, null);
      try {
        const conv = await apiCreateConversation(payload);
        addConversation(conv);
        setActiveConversationId(conv.id);
        return conv;
      } catch (err) {
        const normalised = normaliseApiError(err);
        setError(CREATE_KEY, normalised.message);
        throw normalised;
      } finally {
        setLoading(CREATE_KEY, false);
      }
    },
    [addConversation, setActiveConversationId, setLoading, setError],
  );

  return {
    conversations,
    activeConversationId,
    isLoading,
    isCreating,
    listError,
    createError,
    refresh,
    createConversation,
    setActive: setActiveConversationId,
  };
}
