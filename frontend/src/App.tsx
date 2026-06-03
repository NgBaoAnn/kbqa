import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Activity,
  Bot,
  ChevronDown,
  CircleAlert,
  GraduationCap,
  HeartPulse,
  Loader2,
  Send,
  Sparkles,
  Stethoscope,
  User,
} from "lucide-react";
import { ResponseRenderer } from "./components/ResponseRenderer";
import { getHealth, queryMedical } from "./services/api";
import type { ApiError, HealthResponse, Language, QueryMode, QueryResponse } from "./types/api";

type ChatMessage =
  | {
      id: string;
      role: "user";
      content: string;
      createdAt: string;
    }
  | {
      id: string;
      role: "assistant";
      response: QueryResponse;
      createdAt: string;
    }
  | {
      id: string;
      role: "error";
      content: string;
      createdAt: string;
    };

const chips = [
  {
    label: "Triệu chứng",
    icon: Stethoscope,
    prompt: "Tôi bị đau đầu và sốt, có thể là dấu hiệu của bệnh gì?",
  },
  {
    label: "Tra cứu bệnh",
    icon: HeartPulse,
    prompt: "Bệnh tiểu đường có những triệu chứng gì?",
  },
  {
    label: "Học y khoa",
    icon: GraduationCap,
    prompt: "Giải thích ngắn gọn huyết áp cao là gì.",
  },
  {
    label: "AI gợi ý",
    icon: Sparkles,
    prompt: "Các dấu hiệu nguy hiểm của đau ngực là gì?",
  },
];

const modes: QueryMode[] = ["naive", "local", "global", "hybrid", "mix"];

function nowLabel() {
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function healthLabel(health: HealthResponse | null, error: string | null) {
  if (error) return "Offline";
  if (!health) return "Checking";
  if (health.status === "healthy") return "Ready";
  return health.status;
}

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [language, setLanguage] = useState<Language>("vi");
  const [mode, setMode] = useState<QueryMode>("hybrid");
  const [isSending, setIsSending] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const canSubmit = question.trim().length > 0 && !isSending;
  const hasMessages = messages.length > 0;

  useEffect(() => {
    let ignore = false;

    getHealth()
      .then((payload) => {
        if (!ignore) {
          setHealth(payload);
          setHealthError(null);
        }
      })
      .catch((error: ApiError) => {
        if (!ignore) {
          setHealthError(error.message);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isSending]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmed = question.trim();
    if (!trimmed) return;

    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        createdAt: nowLabel(),
      },
    ]);
    setQuestion("");
    setIsSending(true);

    try {
      const response = await queryMedical({
        question: trimmed,
        language,
        mode,
      });

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          response,
          createdAt: nowLabel(),
        },
      ]);
    } catch (error) {
      const apiError = error as ApiError;
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "error",
          content: apiError.message || "Không thể nhận phản hồi từ hệ thống.",
          createdAt: nowLabel(),
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className={`app-shell ${hasMessages ? "conversation-mode" : "welcome-mode"}`}>
      <header className="top-strip">
        <div className="plan-pill">
          <span>AegisHealth</span>
          <span>·</span>
          <button type="button">KBQA</button>
        </div>
        <div
          className={`health-dot ${health?.status ?? "unknown"}`}
          title={healthError ?? healthLabel(health, healthError)}
          aria-label={healthLabel(health, healthError)}
        >
          <Activity size={16} />
        </div>
      </header>

      <section className="stage" aria-label="Medical QA chat">
        {!hasMessages ? (
          <div className="hero-title">
            <h1>Hỏi đáp y tế cùng AegisHealth</h1>
          </div>
        ) : null}

        {hasMessages ? (
          <div className="message-list" ref={listRef}>
            {messages.map((message) => {
              if (message.role === "user") {
                return (
                  <article key={message.id} className="message user-message">
                    <div className="avatar">
                      <User size={17} />
                    </div>
                    <div className="bubble">
                      <p>{message.content}</p>
                      <time>{message.createdAt}</time>
                    </div>
                  </article>
                );
              }

              if (message.role === "error") {
                return (
                  <article key={message.id} className="message assistant-message">
                    <div className="avatar error-avatar">
                      <CircleAlert size={17} />
                    </div>
                    <div className="bubble error-bubble">
                      <p>{message.content}</p>
                      <time>{message.createdAt}</time>
                    </div>
                  </article>
                );
              }

              return (
                <article key={message.id} className="message assistant-message">
                  <div className="avatar">
                    <Bot size={17} />
                  </div>
                  <div className="bubble assistant-bubble">
                    <ResponseRenderer response={message.response} />
                    <div className="meta-row">
                      <span>{message.response.metadata.engine}</span>
                      <span>{message.response.metadata.execution_time_ms.toFixed(0)} ms</span>
                      <span>{message.response.metadata.source_count} nguồn</span>
                      <time>{message.createdAt}</time>
                    </div>
                  </div>
                </article>
              );
            })}

            {isSending ? (
              <article className="message assistant-message">
                <div className="avatar">
                  <Bot size={17} />
                </div>
                <div className="bubble pending-bubble">
                  <Loader2 size={17} className="spin" />
                  <span>Đang phân tích</span>
                </div>
              </article>
            ) : null}
          </div>
        ) : null}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="How can I help you today?"
            rows={1}
            maxLength={1000}
          />

          <div className="composer-bar">
            <div className="composer-controls">
              <label className="select-pill">
                <span>{mode}</span>
                <select value={mode} onChange={(event) => setMode(event.target.value as QueryMode)}>
                  {modes.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
                <ChevronDown size={13} />
              </label>

              <button
                className="text-toggle"
                type="button"
                onClick={() => setLanguage(language === "vi" ? "en" : "vi")}
              >
                {language.toUpperCase()}
              </button>

              <button className="send-button" type="submit" disabled={!canSubmit} aria-label="Gửi câu hỏi">
                {isSending ? <Loader2 size={20} className="spin" /> : <Send size={20} />}
              </button>
            </div>
          </div>
        </form>

        {!hasMessages ? (
          <div className="chip-row">
            {chips.map((chip) => {
              const Icon = chip.icon;
              return (
                <button key={chip.label} type="button" onClick={() => setQuestion(chip.prompt)}>
                  <Icon size={18} />
                  <span>{chip.label}</span>
                </button>
              );
            })}
          </div>
        ) : null}
      </section>
    </main>
  );
}

export default App;
