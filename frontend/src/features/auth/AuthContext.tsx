/**
 * Auth context — provides current user and session state to the whole app.
 *
 * Responsibilities:
 *  - Subscribe to Supabase auth state changes.
 *  - Fetch /api/v1/me after session is established.
 *  - Expose signIn / signOut helpers.
 *  - Surface USER_INACTIVE state for blocked users.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase, signIn as supabaseSignIn, signOut as supabaseSignOut } from "../../services/supabase";
import { getMe } from "../../services/api";
import type { CurrentUserResponse } from "../../types/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type AuthStatus =
  | "loading"       // initial session check
  | "unauthenticated"
  | "authenticated"
  | "inactive";     // USER_INACTIVE from backend

interface AuthContextValue {
  status: AuthStatus;
  session: Session | null;
  user: CurrentUserResponse | null;
  authError: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<CurrentUserResponse | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  // Fetch backend /me after a valid session is available.
  const fetchProfile = useCallback(async (currentSession: Session) => {
    setSession(currentSession);
    setAuthError(null);

    try {
      const profile = await getMe();
      setUser(profile);
      setStatus("authenticated");
    } catch (err: unknown) {
      const apiErr = err as { status?: number; error_code?: string; message?: string };
      if (apiErr.status === 403 && apiErr.error_code === "USER_INACTIVE") {
        setStatus("inactive");
        setUser(null);
      } else if (apiErr.status === 401) {
        setStatus("unauthenticated");
        setSession(null);
        setUser(null);
      } else {
        // Backend unavailable — still mark authenticated so user can retry.
        // Provide a degraded experience rather than blocking login.
        setUser(null);
        setStatus("authenticated");
        setAuthError(
          apiErr.message ?? "Không thể kết nối backend. Một số tính năng có thể bị giới hạn."
        );
      }
    }
  }, []);

  // Bootstrap: read existing session on mount.
  useEffect(() => {
    let cancelled = false;

    void supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return;
      if (data.session) {
        fetchProfile(data.session);
      } else {
        setStatus("unauthenticated");
      }
    });

    return () => {
      cancelled = true;
    };
  }, [fetchProfile]);

  // Subscribe to auth state changes (login, logout, token refresh).
  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange(
      (_event: string, newSession: import("@supabase/supabase-js").Session | null) => {
        if (newSession) {
          fetchProfile(newSession);
        } else {
          setStatus("unauthenticated");
          setSession(null);
          setUser(null);
        }
      }
    );

    return () => {
      data.subscription.unsubscribe();
    };
  }, [fetchProfile]);

  const handleSignIn = useCallback(
    async (email: string, password: string) => {
      setAuthError(null);
      const { error } = await supabaseSignIn(email, password);
      if (error) {
        setAuthError(error.message);
      }
      // If successful, onAuthStateChange fires and calls fetchProfile.
    },
    []
  );

  const handleSignOut = useCallback(async () => {
    await supabaseSignOut();
    setUser(null);
    setSession(null);
    setStatus("unauthenticated");
    setAuthError(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        status,
        session,
        user,
        authError,
        signIn: handleSignIn,
        signOut: handleSignOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
