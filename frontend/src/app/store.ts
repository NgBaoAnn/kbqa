/**
 * Global Zustand store — Phase 6 (Clean Architecture Frontend).
 *
 * Slices:
 *   auth        — mirrors AuthContext for store-based selectors
 *   conversations — list + active conversation
 *   preferences — user personalisation settings (cached from backend)
 *   ui          — transient loading/error flags
 *
 * Design rules:
 *  - Store holds STATE only. No API calls here.
 *  - API calls live in services/api.ts.
 *  - Hooks (hooks/) orchestrate: call API → update store → return state.
 *  - Components may read store via selectors, but prefer hooks for side-effects.
 *  - AuthContext remains the primary auth provider; this store MIRRORS it
 *    for cases where consuming AuthContext would require deep prop drilling.
 */

import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type {
  ConversationSummary,
  CurrentUserResponse,
  UserPreferences,
} from "../types/api";

// ── Auth slice ────────────────────────────────────────────────────────────────

export type AuthStatus = "loading" | "unauthenticated" | "authenticated" | "inactive";

interface AuthSlice {
  authStatus: AuthStatus;
  user: CurrentUserResponse | null;
  /** Set by AuthContext after Supabase + /me resolve. */
  setAuth: (status: AuthStatus, user: CurrentUserResponse | null) => void;
  clearAuth: () => void;
}

// ── Conversations slice ───────────────────────────────────────────────────────

interface ConversationsSlice {
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  setConversations: (list: ConversationSummary[]) => void;
  addConversation: (conv: ConversationSummary) => void;
  setActiveConversationId: (id: string | null) => void;
  /** Remove a conversation from the list (optimistic delete). */
  removeConversation: (id: string) => void;
}

// ── Preferences slice ─────────────────────────────────────────────────────────

interface PreferencesSlice {
  preferences: UserPreferences | null;
  prefsLoaded: boolean;
  setPreferences: (prefs: UserPreferences) => void;
  clearPreferences: () => void;
}

// ── UI slice ──────────────────────────────────────────────────────────────────

interface UiSlice {
  /** Keyed loading flags — e.g. "conversations:list", "preferences:load" */
  loading: Record<string, boolean>;
  /** Keyed error messages — same keys as loading */
  errors: Record<string, string | null>;
  setLoading: (key: string, value: boolean) => void;
  setError: (key: string, message: string | null) => void;
  clearErrors: () => void;
}

// ── Combined store ────────────────────────────────────────────────────────────

export type AppStore = AuthSlice & ConversationsSlice & PreferencesSlice & UiSlice;

export const useAppStore = create<AppStore>()(
  devtools(
    (set) => ({
      // ── Auth ─────────────────────────────────────────────────────────────
      authStatus: "loading",
      user: null,
      setAuth: (status, user) =>
        set({ authStatus: status, user }, false, "auth/setAuth"),
      clearAuth: () =>
        set({ authStatus: "unauthenticated", user: null }, false, "auth/clearAuth"),

      // ── Conversations ─────────────────────────────────────────────────────
      conversations: [],
      activeConversationId: null,
      setConversations: (list) =>
        set({ conversations: list }, false, "conversations/setConversations"),
      addConversation: (conv) =>
        set(
          (s) => ({ conversations: [conv, ...s.conversations] }),
          false,
          "conversations/addConversation",
        ),
      setActiveConversationId: (id) =>
        set({ activeConversationId: id }, false, "conversations/setActive"),
      removeConversation: (id) =>
        set(
          (s) => ({
            conversations: s.conversations.filter((c) => c.id !== id),
            activeConversationId:
              s.activeConversationId === id ? null : s.activeConversationId,
          }),
          false,
          "conversations/remove",
        ),

      // ── Preferences ───────────────────────────────────────────────────────
      preferences: null,
      prefsLoaded: false,
      setPreferences: (prefs) =>
        set({ preferences: prefs, prefsLoaded: true }, false, "prefs/setPreferences"),
      clearPreferences: () =>
        set({ preferences: null, prefsLoaded: false }, false, "prefs/clear"),

      // ── UI ────────────────────────────────────────────────────────────────
      loading: {},
      errors: {},
      setLoading: (key, value) =>
        set(
          (s) => ({ loading: { ...s.loading, [key]: value } }),
          false,
          `ui/loading/${key}`,
        ),
      setError: (key, message) =>
        set(
          (s) => ({ errors: { ...s.errors, [key]: message } }),
          false,
          `ui/error/${key}`,
        ),
      clearErrors: () => set({ errors: {} }, false, "ui/clearErrors"),
    }),
    { name: "kbqa-store" },
  ),
);

// ── Typed selectors (memoization-friendly) ────────────────────────────────────

/** Select auth state without re-rendering on unrelated store changes. */
export const selectAuth = (s: AppStore) =>
  ({ authStatus: s.authStatus, user: s.user }) as const;

export const selectConversations = (s: AppStore) => s.conversations;
export const selectActiveConversationId = (s: AppStore) => s.activeConversationId;
export const selectPreferences = (s: AppStore) => s.preferences;
export const selectIsLoading = (key: string) => (s: AppStore) =>
  s.loading[key] ?? false;
export const selectError = (key: string) => (s: AppStore) =>
  s.errors[key] ?? null;
