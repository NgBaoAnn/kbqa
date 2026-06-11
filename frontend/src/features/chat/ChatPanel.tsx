/**
 * ChatPanel — Claude-style chat workspace (Sprint 2).
 *
 * Sprint 2 additions:
 *  - Real API integration (no mock): POST /api/v1/conversations/{id}/messages
 *  - Source/citation panel per assistant message (SourcePanel)
 *  - Feedback controls per assistant message (FeedbackControls)
 *  - Disambiguation option click → pre-fills composer
 *  - Suggested questions → pre-fills composer
 *  - Friendly error messages per HTTP status code
 *  - History loaded from backend on mount (reload-safe)
 *  - Loading states: conversation load, sending, pending assistant
 *  - Disabled submit while sending
 */

import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  Bot,
  CircleAlert,
  Loader2,
  Send,
} from "lucide-react";
import { getConversation, sendMessage } from "../../services/api";
import type {
  ChatResponse,
  ChatSource,
  ConversationSummary,
  MessageRecord,
  SafetyPayload,
} from "../../types/api";
import { ChatResponseRenderer } from "../../components/ResponseRenderer";
import { SourcePanel } from "../../components/SourcePanel";
import { FeedbackControls } from "../../components/FeedbackControls";

// ── Types ─────────────────────────────────────────────────────────────────────

type UIMessage =
  | { kind: "record"; data: MessageRecord; sources?: ChatSource[] }
  | { kind: "optimistic-user"; id: string; content: string; createdAt: string }
  | { kind: "optimistic-sending" }
  | { kind: "error"; id: string; content: string };

function timeLabel() {
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

// ── Friendly error messages ───────────────────────────────────────────────────

function friendlyError(err: unknown): string {
  const apiErr = err as { status?: number; message?: string; error_code?: string };
  if (apiErr.error_code === "AUTHENTICATION_REQUIRED" || apiErr.status === 401) {
    return "Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.";
  }
  if (apiErr.status === 403) {
    return "Tài khoản không có quyền truy cập tính năng này.";
  }
  if (apiErr.status === 404) {
    return "Không tìm thấy hội thoại. Vui lòng chọn hoặc tạo hội thoại mới.";
  }
  if (apiErr.status && apiErr.status >= 500) {
    return "Hệ thống đang gặp sự cố. Vui lòng thử lại sau ít phút.";
  }
  return apiErr.message ?? "Không nhận được phản hồi. Vui lòng thử lại.";
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyChat({ onSuggest }: { onSuggest: (text: string) => void }) {
  const suggestions = [
    "Bệnh tiểu đường có triệu chứng gì?",
    "Khi nào nên đến cấp cứu vì đau ngực?",
    "Thuốc hạ áp loại nào phổ biến nhất?",
    "Phân biệt cúm và COVID-19 như thế nào?",
  ];

  return (
    <div className="chat-empty">
      <Bot size={44} className="chat-empty-icon" />
      <h2 className="chat-empty-heading">AegisHealth KBQA</h2>
      <p className="chat-empty-text">
        Đặt câu hỏi y tế và nhận thông tin từ Knowledge Graph.
      </p>
      <div className="chat-suggestions">
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            className="suggestion-chip"
            onClick={() => onSuggest(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Individual message renderers ──────────────────────────────────────────────

function UserMsg({ content, time }: { content: string; time: string }) {
  return (
    <div className="message user-message">
      <div className="user-bubble">
        <p>{content}</p>
      </div>
      <time className="user-time">{time}</time>
    </div>
  );
}

interface AssistantMsgProps {
  response: ChatResponse;
  time: string;
  onComposerFill?: (text: string) => void;
}

function AssistantMsg({ response, time, onComposerFill }: AssistantMsgProps) {
  return (
    <div className="message assistant-message">
      <div className="assistant-header">
        <div className="assistant-avatar" aria-hidden="true">
          <Bot size={15} />
        </div>
        <span className="assistant-name">AegisHealth</span>
      </div>
      <div className="assistant-body">
        <ChatResponseRenderer
          response={response}
          onDisambiguationSelect={onComposerFill}
        />

        {/* Sources panel */}
        {response.sources && response.sources.length > 0 && (
          <SourcePanel sources={response.sources} />
        )}

        <div className="message-footer">
          <div className="meta-row">
            {response.metadata.engine !== "unknown" &&
              response.metadata.engine !== "error" ? (
              <span>{response.metadata.engine}</span>
            ) : null}
            {response.metadata.execution_time_ms > 0 ? (
              <span>{response.metadata.execution_time_ms.toFixed(0)} ms</span>
            ) : null}
            {response.metadata.source_count > 0 ? (
              <span>{response.metadata.source_count} nguồn</span>
            ) : null}
            <time>{time}</time>
          </div>

          {/* Feedback controls */}
          <FeedbackControls messageId={response.message_id} />
        </div>
      </div>
    </div>
  );
}

interface RecordMsgProps {
  record: MessageRecord;
  sources?: ChatSource[];
  onComposerFill?: (text: string) => void;
}

function RecordMsg({ record, sources, onComposerFill }: RecordMsgProps) {
  const time = new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(record.created_at));

  if (record.role === "user") {
    return <UserMsg content={record.content} time={time} />;
  }

  if (record.role === "assistant") {
    const safetyData = record.safety as SafetyPayload | null | undefined;
    const synthetic: ChatResponse = {
      conversation_id: "",
      message_id: record.id,
      status: "success",
      response_type: record.response_type ?? "text",
      answer: record.content,
      data: record.data ?? null,
      sources: sources ?? record.sources ?? [],
      safety: safetyData ?? {
        level: "normal",
        requires_emergency_notice: false,
        disclaimer: "Thông tin chỉ mang tính chất tham khảo.",
      },
      suggested_questions: [],
      metadata: {
        engine: (record.metadata?.engine as string) ?? "—",
        query_mode: (record.metadata?.query_mode as string) ?? "—",
        execution_time_ms: (record.metadata?.execution_time_ms as number) ?? 0,
        source_count: (record.metadata?.source_count as number) ?? 0,
        cypher: null,
      },
    };
    return (
      <AssistantMsg
        response={synthetic}
        time={time}
        onComposerFill={onComposerFill}
      />
    );
  }

  return null;
}

function PendingMsg() {
  return (
    <div className="message pending-message">
      <div className="pending-bubble">
        <div className="assistant-avatar" aria-hidden="true">
          <Bot size={15} />
        </div>
        <div className="typing-dots">
          <span /><span /><span />
        </div>
      </div>
    </div>
  );
}

function ErrorMsg({ content }: { content: string }) {
  return (
    <div className="message error-message">
      <div className="error-bubble">
        <CircleAlert size={15} className="error-bubble-icon" />
        <span>{content}</span>
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

interface ChatPanelProps {
  conversation: ConversationSummary;
}

export function ChatPanel({ conversation }: ChatPanelProps) {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSubmit = question.trim().length > 0 && !isSending && loadState === "ready";

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior, block: "end" });
  }, []);

  // ── Load conversation history from backend ──────────────────────────────

  const loadDetail = useCallback(async () => {
    setLoadState("loading");
    setLoadError(null);
    setMessages([]);
    try {
      const detail = await getConversation(conversation.id);
      setMessages(
        detail.messages.map((m) => ({
          kind: "record" as const,
          data: m,
          sources: m.sources ?? [],
        }))
      );
      setLoadState("ready");
    } catch (err: unknown) {
      setLoadError(friendlyError(err));
      setLoadState("error");
    }
  }, [conversation.id]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  useEffect(() => {
    scrollToBottom(messages.length <= 1 ? "instant" : "smooth");
  }, [messages, scrollToBottom]);

  // ── Auto-resize textarea ────────────────────────────────────────────────

  function handleTextareaChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setQuestion(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  /** Pre-fill composer from disambiguation / suggested questions */
  function fillComposer(text: string) {
    setQuestion(text);
    setTimeout(() => textareaRef.current?.focus(), 50);
  }

  // ── Send message ────────────────────────────────────────────────────────

  async function handleSubmit(e?: FormEvent) {
    e?.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isSending) return;

    const now = timeLabel();
    setQuestion("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    setIsSending(true);

    // Optimistic user message + pending placeholder
    setMessages((prev) => [
      ...prev,
      { kind: "optimistic-user", id: crypto.randomUUID(), content: trimmed, createdAt: now },
      { kind: "optimistic-sending" },
    ]);

    try {
      const response = await sendMessage(conversation.id, { question: trimmed });

      setMessages((prev) => {
        const withoutPending = prev.filter((m) => m.kind !== "optimistic-sending");
        return [
          ...withoutPending,
          {
            kind: "record",
            data: {
              id: response.message_id,
              role: "assistant",
              content: response.answer,
              response_type: response.response_type,
              data: response.data ?? null,
              safety: response.safety,
              metadata: response.metadata as unknown as Record<string, unknown>,
              created_at: new Date().toISOString(),
            },
            // Preserve the full ChatResponse sources so SourcePanel works
            sources: response.sources ?? [],
          },
        ];
      });
    } catch (err: unknown) {
      setMessages((prev) => {
        const withoutPending = prev.filter((m) => m.kind !== "optimistic-sending");
        return [
          ...withoutPending,
          {
            kind: "error",
            id: crypto.randomUUID(),
            content: friendlyError(err),
          },
        ];
      });
    } finally {
      setIsSending(false);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }

  const hasMessages = messages.some(
    (m) => m.kind === "record" || m.kind === "optimistic-user"
  );

  return (
    <div className="chat-panel">
      {/* ── Messages area ── */}
      <div className="chat-messages">
        {loadState === "loading" && (
          <div className="chat-state-center">
            <Loader2 size={22} className="spin" />
            <span>Đang tải hội thoại…</span>
          </div>
        )}

        {loadState === "error" && (
          <div className="chat-state-center chat-state-error">
            <AlertCircle size={22} />
            <span>{loadError}</span>
            <button type="button" className="link-btn" onClick={loadDetail}>
              Thử lại
            </button>
          </div>
        )}

        {loadState === "ready" && !hasMessages && (
          <EmptyChat onSuggest={(text) => setQuestion(text)} />
        )}

        {loadState === "ready" && hasMessages && (
          <div className="chat-messages-inner">
            {messages.map((msg, idx) => {
              if (msg.kind === "record") {
                return (
                  <RecordMsg
                    key={msg.data.id}
                    record={msg.data}
                    sources={msg.sources}
                    onComposerFill={fillComposer}
                  />
                );
              }
              if (msg.kind === "optimistic-user") {
                return <UserMsg key={msg.id} content={msg.content} time={msg.createdAt} />;
              }
              if (msg.kind === "optimistic-sending") {
                return <PendingMsg key={`pending-${idx}`} />;
              }
              if (msg.kind === "error") {
                return <ErrorMsg key={msg.id} content={msg.content} />;
              }
              return null;
            })}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* ── Composer ── */}
      <div className="composer-wrapper">
        <div className="composer-inner">
          <form
            className="composer"
            id="chat-composer"
            onSubmit={handleSubmit}
            aria-label="Nhập câu hỏi"
          >
            <textarea
              ref={textareaRef}
              id="chat-input"
              value={question}
              onChange={handleTextareaChange}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Hỏi về sức khỏe… (Enter để gửi, Shift+Enter xuống dòng)"
              rows={1}
              maxLength={2000}
              disabled={isSending || loadState !== "ready"}
              autoComplete="off"
              autoFocus
            />
            <div className="composer-bar">
              <span className="composer-hint">
                {isSending
                  ? "Đang gửi…"
                  : question.length > 0
                  ? `${question.length}/2000`
                  : ""}
              </span>
              <button
                id="chat-send-btn"
                type="submit"
                className="send-button"
                disabled={!canSubmit}
                aria-label="Gửi câu hỏi"
              >
                {isSending ? (
                  <Loader2 size={18} className="spin" />
                ) : (
                  <Send size={17} />
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
