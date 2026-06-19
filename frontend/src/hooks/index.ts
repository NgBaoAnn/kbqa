/**
 * Shared React hooks — barrel export.
 *
 * Phase 6 (Clean Architecture Frontend):
 *   useApi           — generic one-shot API call with loading/error state
 *   useStream        — SSE streaming chat messages
 *   useConversations — conversation list + creation, synced to Zustand store
 *   usePreferences   — user preferences load/update, synced to Zustand store
 *   normaliseApiError — utility to normalise any thrown value → ApiError
 *
 * Usage:
 *   import { useApi, useStream, useConversations, usePreferences } from "../hooks";
 */

export { useApi, normaliseApiError } from "./useApi";
export type { UseApiOptions } from "./useApi";

export { useStream } from "./useStream";
export type { UseStreamState, UseStreamActions } from "./useStream";

export { useConversations } from "./useConversations";

export { usePreferences } from "./usePreferences";
