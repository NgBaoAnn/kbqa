/**
 * AdminDashboard — S3-FE-03 & S3-FE-04
 *
 * Two sections:
 *   1. Operational metrics cards + engine usage bar chart
 *   2. Pending review queue table
 *
 * Requires admin role. The `get_current_user` dependency in AppShell
 * already prevents non-admins from seeing the nav link; this component
 * adds a secondary guard for direct renders.
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Clock,
  Loader2,
  MessageSquare,
  RefreshCw,
  ShieldAlert,
  ThumbsDown,
} from "lucide-react";
import { getAdminMetrics, getReviewQueue } from "../../services/api";
import type { AdminMetricsResponse, ReviewItemRecord, ReviewQueueResponse } from "../../types/api";

const QUEUE_PAGE_SIZE = 10;

// ── Metric card ───────────────────────────────────────────────────────────────

interface MetricCardProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  colorClass: string;
}

function MetricCard({ label, value, sub, icon, colorClass }: MetricCardProps) {
  return (
    <div className={`metric-card ${colorClass}`}>
      <div className="metric-card-icon">{icon}</div>
      <div className="metric-card-body">
        <div className="metric-value">{value}</div>
        <div className="metric-label">{label}</div>
        {sub && <div className="metric-sub">{sub}</div>}
      </div>
    </div>
  );
}

// ── Engine usage bar chart (pure CSS) ────────────────────────────────────────

function EngineUsageChart({ usage }: { usage: Record<string, number> }) {
  const entries = Object.entries(usage).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (entries.length === 0) return null;

  const ENGINE_COLORS: Record<string, string> = {
    lightrag: "var(--engine-lightrag)",
    cypher_direct: "var(--engine-cypher)",
    mock: "var(--engine-mock)",
  };

  return (
    <div className="engine-chart">
      <h3 className="engine-chart-title">Engine Usage</h3>
      <div className="engine-bars">
        {entries.map(([engine, count]) => {
          const pct = total > 0 ? (count / total) * 100 : 0;
          const color = ENGINE_COLORS[engine] ?? "var(--engine-other)";
          return (
            <div key={engine} className="engine-bar-row">
              <div className="engine-bar-label">{engine}</div>
              <div className="engine-bar-track">
                <div
                  className="engine-bar-fill"
                  style={{ width: `${pct.toFixed(1)}%`, background: color }}
                  role="meter"
                  aria-valuenow={count}
                  aria-valuemin={0}
                  aria-valuemax={total}
                  aria-label={`${engine}: ${count} queries`}
                />
              </div>
              <div className="engine-bar-count">{count}</div>
            </div>
          );
        })}
      </div>
      <div className="engine-chart-total">{total} yêu cầu tổng cộng</div>
    </div>
  );
}

// ── Metrics section ───────────────────────────────────────────────────────────

function MetricsSection() {
  const [data, setData] = useState<AdminMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getAdminMetrics()
      .then((res) => {
        setData(res);
        setLastRefresh(new Date());
      })
      .catch((err: { status?: number }) => {
        if (err.status === 403) {
          setError("Chức năng này yêu cầu quyền Quản trị viên.");
        } else {
          setError("Không thể tải metrics. Vui lòng thử lại.");
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="admin-section">
      <div className="admin-section-header">
        <h2 className="admin-section-title"> Metrics Vận Hành</h2>
        <div className="admin-header-actions">
          {data && (
            <span className="admin-refresh-time">
              Cập nhật lúc {lastRefresh.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            type="button"
            className="admin-refresh-btn"
            onClick={load}
            disabled={loading}
            aria-label="Làm mới metrics"
          >
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            Làm mới
          </button>
        </div>
      </div>

      {loading && !data && (
        <div className="admin-state-center">
          <Loader2 size={22} className="spin" />
          <span>Đang tải metrics…</span>
        </div>
      )}

      {error && (
        <div className="admin-state-center admin-state-error">
          <AlertCircle size={20} />
          <span>{error}</span>
          <button type="button" className="link-btn" onClick={load}>Thử lại</button>
        </div>
      )}

      {data && (
        <>
          <div className="metrics-grid">
            <MetricCard
              label="Tổng yêu cầu"
              value={data.request_count.toLocaleString("vi-VN")}
              icon={<MessageSquare size={20} />}
              colorClass="metric--blue"
            />
            <MetricCard
              label="Latency TB"
              value={`${data.average_latency_ms.toFixed(0)} ms`}
              sub={`P95: ${data.p95_latency_ms.toFixed(0)} ms`}
              icon={<Clock size={20} />}
              colorClass="metric--amber"
            />
            <MetricCard
              label="Phản hồi tiêu cực"
              value={`${(data.negative_feedback_rate * 100).toFixed(1)}%`}
              icon={<ThumbsDown size={20} />}
              colorClass={data.negative_feedback_rate > 0.2 ? "metric--red" : "metric--green"}
            />
            <MetricCard
              label="Chờ duyệt"
              value={String(data.pending_review_count)}
              icon={<ShieldAlert size={20} />}
              colorClass={data.pending_review_count > 0 ? "metric--red" : "metric--green"}
            />
          </div>

          <EngineUsageChart usage={data.engine_usage} />
        </>
      )}
    </section>
  );
}

// ── Review Queue section ──────────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  answer_quality: "Chất lượng câu trả lời",
  safety: "An toàn",
  other: "Khác",
};

const REASON_LABELS: Record<string, string> = {
  incorrect: "Sai thông tin",
  unsafe: "Không an toàn",
  unclear: "Không rõ ràng",
  incomplete: "Thiếu thông tin",
  other: "Khác",
};

// ── Review detail panel ───────────────────────────────────────────────────────

function ReviewDetailPanel({
  item,
  onClose,
}: {
  item: ReviewItemRecord;
  onClose: () => void;
}) {
  const date = new Date(item.created_at).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="review-detail-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Chi tiết review">
      <div className="review-detail-panel" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="review-detail-header">
          <div className="review-detail-title">
            <span className={`review-category-badge review-cat--${item.category}`}>
              {CATEGORY_LABELS[item.category] ?? item.category}
            </span>
            <span className={`review-rating-badge review-rating--${item.rating}`}>
              {item.rating === "down" ? "👎 Tiêu cực" : "👍 Tích cực"}
            </span>
          </div>
          <button
            type="button"
            className="review-detail-close"
            onClick={onClose}
            aria-label="Đóng"
          >
            ✕
          </button>
        </div>

        {/* Metadata row */}
        <div className="review-detail-meta">
          <span className="review-detail-meta-item">
            <strong>Lý do:</strong>{" "}
            {item.reason ? (REASON_LABELS[item.reason] ?? item.reason) : "Không chọn"}
          </span>
          <span className="review-detail-meta-item">
            <strong>Thời gian:</strong> {date}
          </span>
          <span className="review-detail-meta-item">
            <strong>Message ID:</strong>{" "}
            <code className="review-detail-id">{item.message_id.slice(0, 8)}…</code>
          </span>
        </div>

        {/* User comment */}
        {item.comment && (
          <div className="review-detail-comment">
            <div className="review-detail-section-label">Bình luận của người dùng</div>
            <blockquote className="review-detail-quote review-detail-quote--comment">
              {item.comment}
            </blockquote>
          </div>
        )}

        {/* Q&A content */}
        <div className="review-detail-qa">
          <div className="review-detail-bubble review-detail-bubble--user">
            <div className="review-detail-section-label">Câu hỏi</div>
            <p className="review-detail-content">
              {item.question_content ?? (
                <em className="review-detail-na">Không tìm thấy câu hỏi gốc</em>
              )}
            </p>
          </div>

          <div className="review-detail-bubble review-detail-bubble--assistant">
            <div className="review-detail-section-label">Câu trả lời bị báo cáo</div>
            <p className="review-detail-content">
              {item.answer_content ?? (
                <em className="review-detail-na">Không có nội dung</em>
              )}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Review queue row ──────────────────────────────────────────────────────────

function ReviewQueueRow({
  item,
  onClick,
}: {
  item: ReviewItemRecord;
  onClick: () => void;
}) {
  const date = new Date(item.created_at);
  const dateStr = date.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  const timeStr = date.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <tr className="review-row review-row--clickable" onClick={onClick} tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
      role="button" aria-label="Xem chi tiết review">
      <td className="review-cell">
        <span className={`review-category-badge review-cat--${item.category}`}>
          {CATEGORY_LABELS[item.category] ?? item.category}
        </span>
      </td>
      <td className="review-cell">
        {item.reason ? (REASON_LABELS[item.reason] ?? item.reason) : "—"}
      </td>
      <td className="review-cell">
        <span className={`review-rating-badge review-rating--${item.rating}`}>
          {item.rating === "down" ? "👎 Tiêu cực" : "👍 Tích cực"}
        </span>
      </td>
      <td className="review-cell review-cell--preview">
        {item.question_content
          ? item.question_content.slice(0, 60) + (item.question_content.length > 60 ? "…" : "")
          : <span className="review-na">—</span>}
      </td>
      <td className="review-cell review-cell--date">
        <span>{dateStr}</span>
        <span className="review-time">{timeStr}</span>
      </td>
    </tr>
  );
}

function ReviewQueueSection() {
  const [data, setData] = useState<ReviewQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [selectedItem, setSelectedItem] = useState<ReviewItemRecord | null>(null);

  const load = useCallback((off: number) => {
    setLoading(true);
    setError(null);
    getReviewQueue(QUEUE_PAGE_SIZE, off)
      .then(setData)
      .catch((err: { status?: number }) => {
        if (err.status === 403) {
          setError("Chức năng này yêu cầu quyền Quản trị viên.");
        } else {
          setError("Không thể tải review queue. Vui lòng thử lại.");
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(offset); }, [load, offset]);

  const totalPages = data ? Math.ceil(data.total / QUEUE_PAGE_SIZE) : 0;
  const currentPage = Math.floor(offset / QUEUE_PAGE_SIZE) + 1;

  return (
    <section className="admin-section">
      <div className="admin-section-header">
        <h2 className="admin-section-title">
           Review Queue
          {data && data.total > 0 && (
            <span className="review-count-badge">{data.total}</span>
          )}
        </h2>
        <button
          type="button"
          className="admin-refresh-btn"
          onClick={() => load(offset)}
          disabled={loading}
          aria-label="Làm mới review queue"
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          Làm mới
        </button>
      </div>

      {loading && !data && (
        <div className="admin-state-center">
          <Loader2 size={22} className="spin" />
          <span>Đang tải review queue…</span>
        </div>
      )}

      {error && (
        <div className="admin-state-center admin-state-error">
          <AlertCircle size={20} />
          <span>{error}</span>
          <button type="button" className="link-btn" onClick={() => load(offset)}>Thử lại</button>
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className="review-empty">
          <ShieldAlert size={36} className="review-empty-icon" />
          <p>Không có mục nào chờ duyệt.</p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="review-table-wrap">
            <table className="review-table" aria-label="Danh sách review queue">
              <thead>
                <tr>
                  <th className="review-th">Phân loại</th>
                  <th className="review-th">Lý do</th>
                  <th className="review-th">Đánh giá</th>
                  <th className="review-th">Câu hỏi (xem trước)</th>
                  <th className="review-th">Thời gian</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <ReviewQueueRow
                    key={item.id}
                    item={item}
                    onClick={() => setSelectedItem(item)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="knowledge-pagination">
              <button
                type="button"
                className="pagination-btn"
                onClick={() => { setOffset((o) => Math.max(0, o - QUEUE_PAGE_SIZE)); }}
                disabled={offset === 0 || loading}
                aria-label="Trang trước"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="pagination-label">
                {currentPage} / {totalPages}
              </span>
              <button
                type="button"
                className="pagination-btn"
                onClick={() => { setOffset((o) => o + QUEUE_PAGE_SIZE); }}
                disabled={!data || offset + QUEUE_PAGE_SIZE >= data.total || loading}
                aria-label="Trang sau"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}

      {selectedItem && (
        <ReviewDetailPanel item={selectedItem} onClose={() => setSelectedItem(null)} />
      )}
    </section>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

export function AdminDashboard() {
  return (
    <div className="admin-shell">
      <div className="admin-content">
        <div className="admin-page-header">
          <h1 className="admin-page-title">
            <ShieldAlert size={22} />
            Quản trị hệ thống
          </h1>
          <p className="admin-page-sub">
            Metrics vận hành và review queue từ phản hồi người dùng.
          </p>
        </div>

        <MetricsSection />
        <ReviewQueueSection />
      </div>
    </div>
  );
}
