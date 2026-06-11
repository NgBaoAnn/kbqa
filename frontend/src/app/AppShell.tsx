/**
 * AppShell — Claude-like chat layout.
 *
 * Layout:
 *  ┌─────────────┬────────────────────────────────────┐
 *  │ Dark sidebar│ Light main area                    │
 *  │ - Brand     │                                    │
 *  │ - New chat  │  ┌──────────────────────────────┐  │
 *  │ - Conv list │  │  Chat / Knowledge / Admin    │  │
 *  │ - Nav links │  └──────────────────────────────┘  │
 *  │ - User info │                                    │
 *  └─────────────┴────────────────────────────────────┘
 *
 * Sprint 3 additions:
 *  - Nav links: "Tra cứu bệnh" (knowledge), "Quản trị" (admin, role=admin only)
 *  - view state: "chat" | "knowledge" | "admin"
 */

import { useState, useEffect, useRef } from "react";
import {
  BookOpen,
  Menu,
  Moon,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import { useAuth } from "../features/auth/AuthContext";
import { ConversationSidebar } from "../features/chat/ConversationSidebar";
import { ChatPanel } from "../features/chat/ChatPanel";
import { KnowledgeExplorer } from "../features/knowledge/KnowledgeExplorer";
import { AdminDashboard } from "../features/admin/AdminDashboard";
import type { ConversationSummary } from "../types/api";

type AppView = "chat" | "knowledge" | "admin";

function WelcomePane() {
  return (
    <div className="welcome-pane">
      <ShieldCheck size={52} className="welcome-icon" />
      <h1 className="welcome-title">AegisHealth KBQA</h1>
      <p className="welcome-sub">
        Chọn hoặc tạo một hội thoại mới từ thanh bên để bắt đầu hỏi đáp y tế.
      </p>
      <p className="welcome-note">
        ⚕ Thông tin chỉ mang tính tham khảo. Luôn hỏi ý kiến bác sĩ cho các
        quyết định y tế quan trọng.
      </p>
    </div>
  );
}

export function AppShell() {
  const { user, signOut } = useAuth();
  const [activeConversation, setActiveConversation] =
    useState<ConversationSummary | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(
    () => window.innerWidth >= 768
  );
  const [newChatTrigger, setNewChatTrigger] = useState(0);
  const [view, setView] = useState<AppView>("chat");
  const overlayRef = useRef<HTMLDivElement>(null);

  // Theme management
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return (localStorage.getItem("kbqa-theme") as "light" | "dark") || "light";
  });

  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    localStorage.setItem("kbqa-theme", theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === "light" ? "dark" : "light"));
  }

  // Close sidebar on resize → desktop
  useEffect(() => {
    function onResize() {
      if (window.innerWidth >= 768) setSidebarOpen(true);
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  function handleSelect(conv: ConversationSummary) {
    setActiveConversation(conv);
    setView("chat");
    if (window.innerWidth < 768) setSidebarOpen(false);
  }

  function handleCreated(conv: ConversationSummary) {
    setActiveConversation(conv);
    setView("chat");
    if (window.innerWidth < 768) setSidebarOpen(false);
  }

  function triggerNewChat() {
    setView("chat");
    setNewChatTrigger((n) => n + 1);
    if (window.innerWidth < 768) setSidebarOpen(false);
  }

  function navigateTo(v: AppView) {
    setView(v);
    // On mobile, close sidebar when navigating to a feature view
    if (window.innerWidth < 768) setSidebarOpen(false);
  }

  const userInitial = (user?.display_name ?? user?.email ?? "U")
    .charAt(0)
    .toUpperCase();

  const isAdmin = user?.role === "admin";

  // Main content renderer
  function renderMain() {
    if (view === "knowledge") {
      return <KnowledgeExplorer />;
    }
    if (view === "admin" && isAdmin) {
      return <AdminDashboard />;
    }
    // Default: chat view
    if (activeConversation) {
      return (
        <ChatPanel
          key={activeConversation.id}
          conversation={activeConversation}
        />
      );
    }
    return <WelcomePane />;
  }

  return (
    <>
      {/* ── Mobile top bar ── */}
      <header className="mobile-header">
        <button
          id="mobile-sidebar-toggle"
          type="button"
          className="icon-btn"
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label="Toggle sidebar"
        >
          {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <span className="mobile-header-brand">AegisHealth KBQA</span>
        <button
          id="mobile-new-chat-btn"
          type="button"
          className="icon-btn"
          onClick={triggerNewChat}
          aria-label="Tạo hội thoại mới"
        >
          <Plus size={20} />
        </button>
      </header>

      {/* ── Sidebar overlay (mobile) ── */}
      <div
        ref={overlayRef}
        className={`sidebar-overlay${sidebarOpen && window.innerWidth < 768 ? " sidebar-overlay--visible" : ""}`}
        onClick={() => setSidebarOpen(false)}
        aria-hidden="true"
      />

      <div className="shell">
        {/* ── Sidebar ── */}
        <aside
          className={`sidebar${sidebarOpen ? " sidebar--open" : ""}`}
          aria-label="Điều hướng"
        >
          {/* Brand row */}
          <div className="sidebar-top">
            <div className="sidebar-brand-row">
              <div className="sidebar-brand">
                <ShieldCheck size={18} className="sidebar-brand-icon" />
                <span className="sidebar-brand-name">AegisHealth</span>
                <span className="sidebar-brand-tag">KBQA</span>
              </div>
            </div>

            {/* New chat button */}
            <button
              id="new-conversation-btn"
              type="button"
              className="new-chat-btn"
              onClick={triggerNewChat}
              aria-label="Tạo hội thoại mới"
            >
              <Plus size={16} />
              Hội thoại mới
            </button>
          </div>

          {/* Conversation list */}
          <ConversationSidebar
            activeId={view === "chat" ? (activeConversation?.id ?? null) : null}
            onSelect={handleSelect}
            onCreated={handleCreated}
            newChatTrigger={newChatTrigger}
          />

          {/* ── Nav links (Sprint 3) ── */}
          <nav className="sidebar-nav" aria-label="Tính năng">
            <div className="sidebar-section-label">Tính năng</div>
            <button
              id="nav-knowledge-btn"
              type="button"
              className={`nav-item${view === "knowledge" ? " nav-item--active" : ""}`}
              onClick={() => navigateTo("knowledge")}
              aria-current={view === "knowledge" ? "page" : undefined}
            >
              <BookOpen size={15} className="nav-item-icon" />
              Tra cứu bệnh
            </button>

            {isAdmin && (
              <button
                id="nav-admin-btn"
                type="button"
                className={`nav-item${view === "admin" ? " nav-item--active" : ""}`}
                onClick={() => navigateTo("admin")}
                aria-current={view === "admin" ? "page" : undefined}
              >
                <ShieldAlert size={15} className="nav-item-icon" />
                Quản trị
              </button>
            )}
          </nav>

          {/* User footer */}
          <div className="sidebar-footer">
            <div className="sidebar-user">
              <div className="sidebar-avatar" aria-hidden="true">
                {userInitial}
              </div>
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">
                  {user?.display_name ?? user?.email ?? "—"}
                </div>
                <div className="sidebar-user-role">
                  {user?.role === "admin" ? "Quản trị viên" : "Người dùng"}
                </div>
              </div>
              <button
                type="button"
                className="sidebar-logout-btn"
                onClick={toggleTheme}
                title={theme === "light" ? "Giao diện tối" : "Giao diện sáng"}
                aria-label="Đổi giao diện"
              >
                {theme === "light" ? <Moon size={15} /> : <Sun size={15} />}
              </button>
              <button
                id="header-signout-btn"
                type="button"
                className="sidebar-logout-btn"
                onClick={signOut}
                title="Đăng xuất"
                aria-label="Đăng xuất"
              >
                <svg
                  width="15" height="15" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                >
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            </div>
          </div>
        </aside>

        {/* ── Main content ── */}
        <main className="shell-main" aria-label="Vùng nội dung chính">
          {renderMain()}
        </main>
      </div>
    </>
  );
}
