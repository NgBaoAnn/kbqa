/**
 * FeedbackControls — thumbs up/down + optional reason + comment for assistant messages.
 *
 * Contract:
 *  - Only renders for assistant messages (caller's responsibility to filter).
 *  - Calls POST /api/v1/messages/{id}/feedback via submitFeedback().
 *  - States: idle → submitting → submitted | error
 *  - "thumbs down" reveals reason selector and optional comment.
 *  - Feedback cannot be changed after submission (immutable UX).
 */

import { useState } from "react";
import { ThumbsUp, ThumbsDown, Flag, Check, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import { submitFeedback } from "../services/api";
import type { FeedbackRating, FeedbackReason } from "../types/api";

// ── Reason options ────────────────────────────────────────────────────────────

const REASON_OPTIONS: { value: FeedbackReason; label: string }[] = [
  { value: "helpful", label: "Hữu ích nhưng muốn phản hồi" },
  { value: "incorrect", label: "Thông tin không chính xác" },
  { value: "unsafe", label: "Nội dung không an toàn" },
  { value: "unclear", label: "Câu trả lời không rõ ràng" },
  { value: "incomplete", label: "Thiếu thông tin quan trọng" },
  { value: "other", label: "Lý do khác" },
];

// ── Component ─────────────────────────────────────────────────────────────────

type FeedbackState = "idle" | "pending-down" | "submitting" | "submitted" | "error";

interface FeedbackControlsProps {
  messageId: string;
}

export function FeedbackControls({ messageId }: FeedbackControlsProps) {
  const [state, setState] = useState<FeedbackState>("idle");
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [reason, setReason] = useState<FeedbackReason | null>(null);
  const [comment, setComment] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showComment, setShowComment] = useState(false);

  async function handleQuickUp() {
    if (state !== "idle") return;
    setRating("up");
    setState("submitting");
    try {
      await submitFeedback(messageId, { rating: "up", reason: "helpful" });
      setState("submitted");
    } catch (err) {
      setErrorMsg((err as { message?: string }).message ?? "Không gửi được phản hồi.");
      setState("error");
    }
  }

  function handleDownClick() {
    if (state !== "idle") return;
    setRating("down");
    setState("pending-down");
  }

  async function handleSubmitDown(e: React.FormEvent) {
    e.preventDefault();
    if (state !== "pending-down") return;
    setState("submitting");
    try {
      await submitFeedback(messageId, {
        rating: "down",
        reason: reason ?? undefined,
        comment: comment.trim() || null,
      });
      setState("submitted");
    } catch (err) {
      setErrorMsg((err as { message?: string }).message ?? "Không gửi được phản hồi.");
      setState("error");
    }
  }

  // ── Submitted state ───────────────────────────────────────────────────────

  if (state === "submitted") {
    return (
      <div className="feedback-submitted" role="status" aria-live="polite">
        <Check size={13} className="feedback-submitted-icon" />
        <span>
          {rating === "up"
            ? "Cảm ơn phản hồi của bạn!"
            : "Đã ghi nhận — nhóm sẽ xem xét câu trả lời này."}
        </span>
      </div>
    );
  }

  // ── Error state ───────────────────────────────────────────────────────────

  if (state === "error") {
    return (
      <div className="feedback-error" role="alert">
        <AlertCircle size={13} />
        <span>{errorMsg}</span>
        <button
          type="button"
          className="link-btn"
          onClick={() => { setState("idle"); setRating(null); setErrorMsg(null); }}
        >
          Thử lại
        </button>
      </div>
    );
  }

  // ── Pending-down: reason + comment form ───────────────────────────────────

  if (state === "pending-down") {
    // isFormSubmitting is always false here (state is "pending-down"),
    // but we need a boolean ref for the disabled prop on submit button.
    // The form's onSubmit sets state to "submitting" which re-renders away from this block.
    return (
      <form className="feedback-form" onSubmit={handleSubmitDown} aria-label="Phản hồi chi tiết">
        <div className="feedback-form-header">
          <ThumbsDown size={13} className="feedback-down-icon" />
          <span>Vì sao câu trả lời chưa tốt?</span>
          <button
            type="button"
            className="feedback-cancel"
            onClick={() => { setState("idle"); setRating(null); }}
            aria-label="Hủy phản hồi"
          >
            ✕
          </button>
        </div>

        <div className="feedback-reasons" role="group" aria-label="Lý do phản hồi">
          {REASON_OPTIONS.map((opt) => (
            <label key={opt.value} className="feedback-reason-label">
              <input
                type="radio"
                name={`feedback-reason-${messageId}`}
                value={opt.value}
                checked={reason === opt.value}
                onChange={() => setReason(opt.value)}
                className="feedback-radio"
              />
              {opt.label}
            </label>
          ))}
        </div>

        <button
          type="button"
          className="feedback-comment-toggle"
          onClick={() => setShowComment((v) => !v)}
          aria-expanded={showComment}
        >
          {showComment ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {showComment ? "Ẩn bình luận" : "Thêm bình luận (tuỳ chọn)"}
        </button>

        {showComment && (
          <textarea
            className="feedback-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Mô tả thêm vấn đề bạn gặp phải…"
            maxLength={1000}
            rows={3}
            aria-label="Bình luận phản hồi"
          />
        )}

        <div className="feedback-form-actions">
          <button
            type="button"
            className="feedback-btn-cancel"
            onClick={() => { setState("idle"); setRating(null); setReason(null); setComment(""); }}
          >
            Bỏ qua
          </button>
          <button
            type="submit"
            className="feedback-btn-submit"
          >
            <Flag size={12} />
            Gửi phản hồi
          </button>
        </div>
      </form>
    );
  }


  // ── Idle: quick thumbs up/down buttons ────────────────────────────────────

  const isSubmitting = state === "submitting";

  return (
    <div className="feedback-controls" role="group" aria-label="Đánh giá câu trả lời">
      <button
        id={`feedback-up-${messageId}`}
        type="button"
        className={`feedback-btn feedback-btn--up${rating === "up" ? " feedback-btn--active" : ""}`}
        onClick={handleQuickUp}
        disabled={isSubmitting}
        aria-label="Câu trả lời hữu ích"
        title="Hữu ích"
      >
        <ThumbsUp size={14} />
      </button>
      <button
        id={`feedback-down-${messageId}`}
        type="button"
        className="feedback-btn feedback-btn--down"
        onClick={handleDownClick}
        disabled={isSubmitting}
        aria-label="Câu trả lời chưa tốt"
        title="Chưa tốt"
      >
        <ThumbsDown size={14} />
      </button>
    </div>
  );
}
