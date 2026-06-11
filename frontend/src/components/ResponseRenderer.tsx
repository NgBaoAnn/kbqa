/**
 * ResponseRenderer — renders assistant response by type.
 *
 * Supported response_type values (Sprint 2):
 *   - text        → Markdown prose
 *   - warning     → Medical warning block (amber border-left)
 *   - table       → Structured data table; fallback to markdown if data absent
 *   - disambiguation → List of entity choices for user to clarify
 *   - source_list → Inline source-list view (delegates to SourcePanel)
 *
 * Safety levels: normal | caution | emergency
 * All renderers are null-safe: data=null never crashes UI.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  ShieldAlert,
  HelpCircle,
  ChevronRight,
} from "lucide-react";
import type { ChatResponse, QueryResponse, SafetyPayload } from "../types/api";

// ── Safety block ──────────────────────────────────────────────────────────────

function SafetyBlock({ safety }: { safety: SafetyPayload }) {
  if (safety.level === "normal" && !safety.requires_emergency_notice) {
    return <p className="safety-disclaimer">{safety.disclaimer}</p>;
  }
  const cls = safety.requires_emergency_notice
    ? "safety-block safety-block--emergency"
    : "safety-block safety-block--caution";
  return (
    <div className={cls} role="alert" aria-live="assertive">
      <ShieldAlert size={15} style={{ flexShrink: 0, marginTop: 1 }} />
      <span>{safety.disclaimer}</span>
    </div>
  );
}

// ── Emergency notice (shown above answer when requires_emergency_notice=true) ──

function EmergencyNotice() {
  return (
    <div className="emergency-notice" role="alert" aria-live="assertive">
      <ShieldAlert size={16} />
      <div>
        <strong>KHẨN CẤP:</strong> Nếu bạn đang gặp tình huống nguy hiểm, hãy gọi
        ngay <strong>115</strong> hoặc đến cơ sở y tế gần nhất.
      </div>
    </div>
  );
}

// ── Markdown renderer ─────────────────────────────────────────────────────────

/**
 * Remove backend-injected [!NOTE] disclaimer lines from markdown.
 *
 * Returns:
 *   cleaned      — answer text with [!NOTE] block stripped (if present)
 *   hadDisclaimer — true only when the original text contained [!NOTE]
 *
 * When hadDisclaimer is false the SafetyBlock for level="normal" is
 * suppressed — no duplicate, no spurious disclaimer on clean answers.
 */
function stripDisclaimerNote(text: string): { cleaned: string; hadDisclaimer: boolean } {
  // Fast path: most answers don't have a [!NOTE] block at all.
  if (!text.includes("[!NOTE]")) return { cleaned: text, hadDisclaimer: false };

  const cleaned = text
    // Remove full GFM alert block: > [!NOTE] ... continuing > lines
    .replace(/^>[ \t]*\[!NOTE\][^\n]*(\n^>[ \t]*[^\n]*)*/gm, "")
    // Remove plain [!NOTE] lines (not in blockquote)
    .replace(/^\[!NOTE\][^\n]*/gm, "")
    // Collapse more than 2 consecutive blank lines into one
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  return { cleaned, hadDisclaimer: true };
}

function MarkdownBody({ content }: { content: string }) {
  const { cleaned } = stripDisclaimerNote(content);
  return (
    <div className="markdown-prose">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleaned}</ReactMarkdown>
    </div>
  );
}


// ── Warning response ──────────────────────────────────────────────────────────

function WarningBody({ answer }: { answer: string }) {
  return (
    <div className="warning-response" role="alert">
      <div className="warning-label">
        <AlertTriangle size={13} />
        Cảnh báo y tế
      </div>
      <MarkdownBody content={answer} />
    </div>
  );
}

// ── Table renderer ────────────────────────────────────────────────────────────

function TableBody({
  data,
  answer,
}: {
  data: Record<string, unknown>[] | Record<string, unknown> | null | undefined;
  answer: string;
}) {
  // Normalise data to a row array
  const rows: Record<string, unknown>[] = Array.isArray(data)
    ? data
    : data && typeof data === "object"
    ? [data]
    : [];

  if (rows.length === 0) {
    // Fallback to markdown when data is absent
    return <MarkdownBody content={answer} />;
  }

  const headers = Object.keys(rows[0]);

  return (
    <div className="table-response">
      {answer && <MarkdownBody content={answer} />}
      <div className="table-wrapper" role="region" aria-label="Bảng dữ liệu">
        <table className="data-table">
          <thead>
            <tr>
              {headers.map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri}>
                {headers.map((h) => (
                  <td key={h}>
                    {typeof row[h] === "object"
                      ? JSON.stringify(row[h])
                      : String(row[h] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Disambiguation renderer ───────────────────────────────────────────────────

interface DisambiguationOption {
  label?: string;
  name?: string;
  description?: string;
  value?: string;
}

function DisambiguationBody({
  answer,
  data,
  onSelect,
}: {
  answer: string;
  data: Record<string, unknown>[] | Record<string, unknown> | null | undefined;
  onSelect?: (label: string) => void;
}) {
  const options: DisambiguationOption[] = Array.isArray(data)
    ? (data as DisambiguationOption[])
    : [];

  return (
    <div className="disambiguation-response">
      <div className="disambiguation-header">
        <HelpCircle size={14} />
        <span>Làm rõ câu hỏi</span>
      </div>
      <MarkdownBody content={answer} />
      {options.length > 0 && (
        <div className="disambiguation-options" role="list" aria-label="Các lựa chọn">
          {options.map((opt, i) => {
            const label = opt.label ?? opt.name ?? opt.value ?? `Lựa chọn ${i + 1}`;
            return (
              <button
                key={i}
                type="button"
                className="disambiguation-option"
                role="listitem"
                onClick={() => onSelect?.(label)}
              >
                <ChevronRight size={13} />
                <span>
                  <strong>{label}</strong>
                  {opt.description && (
                    <span className="disambiguation-desc"> — {opt.description}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── ChatResponseRenderer (new conversation flow) ──────────────────────────────

interface ChatResponseRendererProps {
  response: ChatResponse;
  /** Called when a disambiguation option is clicked — caller can pre-fill composer */
  onDisambiguationSelect?: (label: string) => void;
}

export function ChatResponseRenderer({
  response,
  onDisambiguationSelect,
}: ChatResponseRendererProps) {
  const showEmergency = response.safety?.requires_emergency_notice === true;

  // Detect whether the answer originally contained a backend [!NOTE] block.
  // SafetyBlock for level="normal" is shown ONLY when the backend explicitly
  // included a disclaimer note in the answer text.
  const { hadDisclaimer } = stripDisclaimerNote(response.answer);

  // Show SafetyBlock when:
  //   - caution or emergency (always — these are important safety signals)
  //   - normal + backend included a [!NOTE] in the answer (hadDisclaimer)
  // Do NOT show for normal answers without any disclaimer from backend.
  const showSafetyBlock =
    response.safety &&
    (response.safety.level !== "normal" || hadDisclaimer);

  return (
    <div className="response-block">
      {/* Emergency notice appears before the answer */}
      {showEmergency && <EmergencyNotice />}

      {/* Body varies by response_type */}
      {response.response_type === "warning" ? (
        <WarningBody answer={response.answer} />
      ) : response.response_type === "table" ? (
        <TableBody data={response.data} answer={response.answer} />
      ) : response.response_type === "disambiguation" ? (
        <DisambiguationBody
          answer={response.answer}
          data={response.data}
          onSelect={onDisambiguationSelect}
        />
      ) : (
        /* text | source_list | unknown → markdown */
        <MarkdownBody content={response.answer} />
      )}

      {/* Safety block — see showSafetyBlock logic above */}
      {showSafetyBlock && <SafetyBlock safety={response.safety!} />}

      {/* Suggested follow-up questions */}
      {response.suggested_questions && response.suggested_questions.length > 0 && (
        <div className="suggested-questions">
          <span className="suggested-label">Câu hỏi tiếp theo:</span>
          <div className="suggested-chips">
            {response.suggested_questions.map((q, i) => (
              <button
                key={i}
                type="button"
                className="suggested-chip"
                onClick={() => onDisambiguationSelect?.(q)}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Legacy ResponseRenderer (old /query endpoint) ─────────────────────────────

/** @deprecated Use ChatResponseRenderer for conversation flow. */
export function ResponseRenderer({ response }: { response: QueryResponse }) {
  return (
    <div className="response-block">
      {response.response_type === "warning" ? (
        <div className="warning-response" role="alert">
          <div className="warning-label">
            <AlertTriangle size={13} />
            Cảnh báo y tế
          </div>
          <MarkdownBody content={response.answer} />
        </div>
      ) : (
        <MarkdownBody content={response.answer} />
      )}
    </div>
  );
}
