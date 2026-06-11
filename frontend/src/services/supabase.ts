/**
 * Supabase frontend client.
 *
 * Rules:
 *  - Only uses VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY (public anon key).
 *  - Never uses SUPABASE_SERVICE_ROLE_KEY.
 *  - This file is the single place where the Supabase client is created.
 */

import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

if (!supabaseUrl || !supabaseAnonKey) {
  // Hard-fail early so misconfiguration is obvious in development.
  throw new Error(
    "Missing Supabase env vars. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env"
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

/** Get the current Supabase session access token, or null if not authenticated. */
export async function getAccessToken(): Promise<string | null> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

/** Sign in with email and password via Supabase Auth. */
export async function signIn(email: string, password: string) {
  return supabase.auth.signInWithPassword({ email, password });
}

/** Sign out the current user. */
export async function signOut() {
  return supabase.auth.signOut();
}

/** Subscribe to auth state changes. Returns the unsubscribe function. */
export function onAuthStateChange(
  callback: (event: string, session: import("@supabase/supabase-js").Session | null) => void
) {
  const { data } = supabase.auth.onAuthStateChange(callback);
  return data.subscription.unsubscribe;
}
