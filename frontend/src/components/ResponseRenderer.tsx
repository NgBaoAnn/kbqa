/**
 * ResponseRenderer — renders assistant response by type.
 * Claude-style: no labels, clean markdown flow.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ShieldAlert, AlertTriangle } from "lucide-react";
import type { ChatResponse, QueryResponse, SafetyPayload } from "../types/api";

// ── Safety block ──────────────────────────────────────────────────────────────

function SafetyBlock({ safety }: { safety: SafetyPayload }) {
  if (safety.level === "normal" && !safety.requires_emergency_notice) {
    return (
      <p className="safety-disclaimer">{safety.disclaimer}</p>
    );
  }
  const cls =
    safety.requires_emergency_notice
      ? "safety-block safety-block--emergency"
      : "safety-block safety-block--caution";
  return (
    <div className={cls} role="alert">
      <ShieldAlert size={15} style={{ flexShrink: 0, marginTop: 1 }} />
      <span>{safety.disclaimer}</span>
    </div>
  );
}

// ── Markdown renderer ─────────────────────────────────────────────────────────

function MarkdownBody({ content }: { content: string }) {
  return (
    <div className="markdown-prose">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

// ── Warning response ──────────────────────────────────────────────────────────

function WarningBody({ answer }: { answer: string }) {
  return (
    <div className="warning-response">
      <div className="warning-label">
        <AlertTriangle size={13} />
        Cảnh báo y tế
      </div>
      <MarkdownBody content={answer} />
    </div>
  );
}

// ── ChatResponseRenderer (new conversation flow) ──────────────────────────────

export function ChatResponseRenderer({ response }: { response: ChatResponse }) {
  return (
    <div className="response-block">
      {response.response_type === "warning" ? (
        <WarningBody answer={response.answer} />
      ) : (
        <MarkdownBody content={response.answer} />
      )}
      {response.safety ? <SafetyBlock safety={response.safety} /> : null}
    </div>
  );
}

// ── Legacy ResponseRenderer (old /query endpoint) ─────────────────────────────

/** @deprecated Use ChatResponseRenderer for conversation flow. */
export function ResponseRenderer({ response }: { response: QueryResponse }) {
  return (
    <div className="response-block">
      {response.response_type === "warning" ? (
        <WarningBody answer={response.answer} />
      ) : (
        <MarkdownBody content={response.answer} />
      )}
    </div>
  );
}
