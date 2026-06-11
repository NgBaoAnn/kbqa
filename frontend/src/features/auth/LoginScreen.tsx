/**
 * Login screen — shown when the user is not authenticated.
 * Uses Supabase Auth directly. No credentials are sent to our backend.
 */

import { type FormEvent, useState } from "react";
import { Loader2, LogIn, ShieldCheck } from "lucide-react";
import { useAuth } from "./AuthContext";

export function LoginScreen() {
  const { signIn, authError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    await signIn(email.trim(), password);
    setIsLoading(false);
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <ShieldCheck size={28} className="auth-brand-icon" />
          <div>
            <div className="auth-brand-name">AegisHealth KBQA</div>
            <div className="auth-brand-sub">Hỏi đáp y tế thông minh</div>
          </div>
        </div>

        <h1 className="auth-title">Đăng nhập</h1>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-field">
            <label htmlFor="auth-email" className="auth-label">
              Email
            </label>
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              className="auth-input"
              placeholder="email@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password" className="auth-label">
              Mật khẩu
            </label>
            <input
              id="auth-password"
              type="password"
              autoComplete="current-password"
              className="auth-input"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>

          {authError ? (
            <div className="auth-error" role="alert">
              {authError}
            </div>
          ) : null}

          <button
            id="auth-submit-btn"
            type="submit"
            className="auth-submit"
            disabled={isLoading || !email.trim() || !password}
          >
            {isLoading ? (
              <Loader2 size={18} className="spin" />
            ) : (
              <LogIn size={18} />
            )}
            <span>{isLoading ? "Đang đăng nhập…" : "Đăng nhập"}</span>
          </button>
        </form>

        <p className="auth-disclaimer">
          Tài khoản được cấp bởi quản trị viên hệ thống.
        </p>
      </div>
    </div>
  );
}
