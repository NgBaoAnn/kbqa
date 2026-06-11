/**
 * ConversationSidebar — conversation list only.
 * New chat button and brand are handled by AppShell.
 * Supports newChatTrigger prop to create a new conversation externally.
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { MessageSquare, Loader2, AlertCircle } from "lucide-react";
import { listConversations, createConversation } from "../../services/api";
import type { ConversationSummary } from "../../types/api";

interface ConversationSidebarProps {
  activeId: string | null;
  onSelect: (conversation: ConversationSummary) => void;
  onCreated: (conversation: ConversationSummary) => void;
  /** Increment to trigger new conversation creation from outside */
  newChatTrigger?: number;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return new Intl.DateTimeFormat("vi-VN", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(d);
    }
    return new Intl.DateTimeFormat("vi-VN", {
      day: "2-digit",
      month: "2-digit",
    }).format(d);
  } catch {
    return "";
  }
}

export function ConversationSidebar({
  activeId,
  onSelect,
  onCreated,
  newChatTrigger = 0,
}: ConversationSidebarProps) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const prevTrigger = useRef(newChatTrigger);

  const load = useCallback(async () => {
    setLoadState("loading");
    setLoadError(null);
    try {
      const data = await listConversations();
      setConversations(data.sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
      setLoadState("ready");
    } catch (err: unknown) {
      setLoadError((err as { message?: string }).message ?? "Không thể tải danh sách.");
      setLoadState("error");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // React to external new-chat trigger
  useEffect(() => {
    if (newChatTrigger !== prevTrigger.current) {
      prevTrigger.current = newChatTrigger;
      handleCreateNew();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newChatTrigger]);

  async function handleCreateNew() {
    if (isCreating) return;
    setIsCreating(true);
    try {
      const newConv = await createConversation({ language: "vi" });
      setConversations((prev) => [newConv, ...prev]);
      onCreated(newConv);
    } catch (err: unknown) {
      // Fail silently — parent or user can retry
      console.error("create conversation failed:", err);
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="sidebar-body">
      {loadState === "loading" && (
        <div className="sidebar-placeholder">
          <Loader2 size={16} className="spin" />
          <span>Đang tải…</span>
        </div>
      )}

      {loadState === "error" && (
        <div className="sidebar-placeholder sidebar-error">
          <AlertCircle size={16} />
          <span>{loadError}</span>
          <button type="button" className="link-btn" onClick={load}>
            Thử lại
          </button>
        </div>
      )}

      {loadState === "ready" && conversations.length === 0 && (
        <div className="sidebar-empty">
          <MessageSquare size={26} className="sidebar-empty-icon" />
          <p>Chưa có hội thoại nào.</p>
          <button
            id="sidebar-create-first-btn"
            type="button"
            className="sidebar-empty-cta"
            onClick={handleCreateNew}
            disabled={isCreating}
          >
            {isCreating ? <Loader2 size={14} className="spin" /> : null}
            Bắt đầu hội thoại
          </button>
        </div>
      )}

      {loadState === "ready" && conversations.length > 0 && (
        <>
          <div className="sidebar-section-label">Hôm nay</div>
          <ul className="conv-list" role="list">
            {conversations.map((conv) => (
              <li key={conv.id}>
                <button
                  type="button"
                  className={`conv-item${activeId === conv.id ? " conv-item--active" : ""}`}
                  onClick={() => onSelect(conv)}
                  aria-current={activeId === conv.id ? "true" : undefined}
                  title={conv.title}
                >
                  <span className="conv-item-title">{conv.title}</span>
                  <time className="conv-item-date" dateTime={conv.updated_at}>
                    {formatDate(conv.updated_at)}
                  </time>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
