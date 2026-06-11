/**
 * Shown when the backend returns 403 USER_INACTIVE.
 * The user is authenticated with Supabase but their app profile is disabled.
 */

import { ShieldOff, LogOut } from "lucide-react";
import { useAuth } from "./AuthContext";

export function InactiveScreen() {
  const { signOut, user, session } = useAuth();

  return (
    <div className="auth-screen">
      <div className="auth-card inactive-card">
        <div className="inactive-icon">
          <ShieldOff size={40} />
        </div>
        <h1 className="auth-title">Tài khoản bị vô hiệu hóa</h1>
        <p className="auth-disclaimer" style={{ textAlign: "center", maxWidth: 340 }}>
          Tài khoản của bạn (<strong>{user?.email ?? session?.user?.email ?? "—"}</strong>)
          đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên để được hỗ trợ.
        </p>
        <button
          id="inactive-signout-btn"
          type="button"
          className="auth-submit"
          onClick={signOut}
          style={{ marginTop: 8 }}
        >
          <LogOut size={18} />
          <span>Đăng xuất</span>
        </button>
      </div>
    </div>
  );
}
