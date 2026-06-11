/**
 * App root — mounts the AuthProvider and renders the correct screen
 * based on auth status.
 *
 * States:
 *  loading        → full-page spinner
 *  unauthenticated → LoginScreen
 *  inactive       → InactiveScreen
 *  authenticated  → AppShell
 */

import { Loader2, ShieldCheck } from "lucide-react";
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import { LoginScreen } from "./features/auth/LoginScreen";
import { InactiveScreen } from "./features/auth/InactiveScreen";
import { AppShell } from "./app/AppShell";

function AppContent() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="full-center">
        <ShieldCheck size={32} className="splash-icon" />
        <Loader2 size={24} className="spin" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <LoginScreen />;
  }

  if (status === "inactive") {
    return <InactiveScreen />;
  }

  // status === "authenticated"
  return <AppShell />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
