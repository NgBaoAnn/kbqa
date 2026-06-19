/**
 * usePreferences — loads and updates user preferences, synced to Zustand store.
 *
 * Usage:
 *   const {
 *     preferences, loaded, loading, error,
 *     update, refresh,
 *   } = usePreferences();
 *
 * Features:
 *  - Auto-fetches on first call (if not already loaded in store)
 *  - PATCH partial update via updatePreferences API
 *  - Optimistically updates store on success
 *  - Error is normalised ApiError message string
 */

import { useCallback, useEffect } from "react";
import { getPreferences, updatePreferences } from "../services/api";
import type { UserPreferences, UserPreferencesResponse } from "../types/api";
import { selectPreferences, useAppStore } from "../app/store";
import { normaliseApiError } from "./useApi";

const LOAD_KEY = "preferences:load";
const SAVE_KEY = "preferences:save";

function rowToPrefs(row: UserPreferencesResponse): UserPreferences {
  return {
    language: row.language,
    explanation_level: row.explanation_level,
    answer_style: row.answer_style,
  };
}

export function usePreferences() {
  const preferences = useAppStore(selectPreferences);
  const prefsLoaded = useAppStore((s) => s.prefsLoaded);
  const { setPreferences, setLoading, setError, loading, errors } = useAppStore();

  const isLoading = loading[LOAD_KEY] ?? false;
  const isSaving = loading[SAVE_KEY] ?? false;
  const loadError = errors[LOAD_KEY] ?? null;
  const saveError = errors[SAVE_KEY] ?? null;

  const refresh = useCallback(async () => {
    setLoading(LOAD_KEY, true);
    setError(LOAD_KEY, null);
    try {
      const row = await getPreferences();
      setPreferences(rowToPrefs(row));
    } catch (err) {
      setError(LOAD_KEY, normaliseApiError(err).message);
    } finally {
      setLoading(LOAD_KEY, false);
    }
  }, [setPreferences, setLoading, setError]);

  // Auto-load only if not already in store.
  useEffect(() => {
    if (!prefsLoaded) {
      void refresh();
    }
  }, [prefsLoaded, refresh]);

  /**
   * Partial-update preferences via PATCH /api/v1/me/preferences.
   * Optimistically updates store on success.
   */
  const update = useCallback(
    async (patch: Partial<UserPreferences>): Promise<UserPreferencesResponse> => {
      setLoading(SAVE_KEY, true);
      setError(SAVE_KEY, null);
      try {
        const row = await updatePreferences(patch);
        setPreferences(rowToPrefs(row));
        return row;
      } catch (err) {
        const normalised = normaliseApiError(err);
        setError(SAVE_KEY, normalised.message);
        throw normalised;
      } finally {
        setLoading(SAVE_KEY, false);
      }
    },
    [setPreferences, setLoading, setError],
  );

  return {
    preferences,
    loaded: prefsLoaded,
    isLoading,
    isSaving,
    loadError,
    saveError,
    refresh,
    update,
  };
}
