/**
 * KnowledgeExplorer — S3-FE-01 & S3-FE-02
 *
 * Two-pane knowledge browser:
 *   Left: Search + paginated disease list
 *   Right: Disease detail panel (shown on selection)
 *
 * On mobile: list collapses when detail is open.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
  X,
} from "lucide-react";
import { getDiseaseDetail, listDiseases } from "../../services/api";
import type { DiseaseDetailResponse, DiseaseSummary } from "../../types/api";

const PAGE_SIZE = 20;

// ── Disease Detail Panel ──────────────────────────────────────────────────────

interface DetailSection {
  label: string;
  items: string[];
  colorClass: string;
}

function DetailChip({ text, colorClass }: { text: string; colorClass: string }) {
  return (
    <span className={`detail-chip ${colorClass}`}>{text}</span>
  );
}

function DetailSection({ label, items, colorClass }: DetailSection) {
  if (items.length === 0) return null;
  return (
    <div className="detail-section">
      <h3 className="detail-section-title">
        {label}
        <span className="detail-section-count">{items.length}</span>
      </h3>
      <div className="detail-chips-wrap">
        {items.map((item, i) => (
          <DetailChip key={i} text={item} colorClass={colorClass} />
        ))}
      </div>
    </div>
  );
}

interface DiseaseDetailPanelProps {
  diseaseId: string;
  onBack: () => void;
}

function DiseaseDetailPanel({ diseaseId, onBack }: DiseaseDetailPanelProps) {
  const [data, setData] = useState<DiseaseDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);
    getDiseaseDetail(diseaseId)
      .then(setData)
      .catch(() => setError("Không thể tải chi tiết bệnh. Vui lòng thử lại."))
      .finally(() => setLoading(false));
  }, [diseaseId]);

  return (
    <div className="disease-detail">
      <div className="disease-detail-header">
        <button
          type="button"
          className="detail-back-btn"
          onClick={onBack}
          aria-label="Quay lại danh sách"
        >
          <ArrowLeft size={16} />
          Danh sách
        </button>
      </div>

      {loading && (
        <div className="knowledge-state-center">
          <Loader2 size={22} className="spin" />
          <span>Đang tải…</span>
        </div>
      )}

      {error && (
        <div className="knowledge-state-center knowledge-state-error">
          <AlertCircle size={20} />
          <span>{error}</span>
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setLoading(true);
              setError(null);
              getDiseaseDetail(diseaseId)
                .then(setData)
                .catch(() => setError("Không thể tải chi tiết bệnh."))
                .finally(() => setLoading(false));
            }}
          >
            Thử lại
          </button>
        </div>
      )}

      {data && (
        <div className="disease-detail-body">
          <div className="disease-detail-title-row">
            <h2 className="disease-detail-name">{data.disease_name}</h2>
            {data.metadata?.disease_category != null && (
              <span className="disease-category-badge">
                {String(data.metadata.disease_category)}
              </span>
            )}
          </div>

          {data.description && (
            <p className="disease-description">{data.description}</p>
          )}

          {data.metadata?.disease_cause != null && (
            <div className="disease-cause-block">
              <span className="disease-cause-label">Nguyên nhân:</span>{" "}
              <span>{String(data.metadata.disease_cause)}</span>
            </div>
          )}

          <div className="detail-sections">
            <DetailSection
              label="Triệu chứng"
              items={data.symptoms}
              colorClass="chip--symptom"
            />
            <DetailSection
              label="Phương pháp điều trị"
              items={data.treatments}
              colorClass="chip--treatment"
            />
            <DetailSection
              label="Thuốc"
              items={data.medicines}
              colorClass="chip--medicine"
            />
            <DetailSection
              label="Lời khuyên & Dinh dưỡng"
              items={data.advice}
              colorClass="chip--advice"
            />
          </div>

          {data.symptoms.length === 0 &&
            data.treatments.length === 0 &&
            data.medicines.length === 0 &&
            data.advice.length === 0 && (
              <div className="knowledge-empty">
                <p>Chưa có dữ liệu chi tiết cho bệnh này.</p>
              </div>
            )}

          <div className="disease-source-note">
            <BookOpen size={12} />
            Nguồn: Neo4j VietMedKG
          </div>
        </div>
      )}
    </div>
  );
}

// ── Disease List ──────────────────────────────────────────────────────────────

interface DiseaseListProps {
  items: DiseaseSummary[];
  onSelect: (id: string) => void;
  selectedId: string | null;
}

function DiseaseList({ items, onSelect, selectedId }: DiseaseListProps) {
  if (items.length === 0) {
    return (
      <div className="knowledge-empty">
        <BookOpen size={32} className="knowledge-empty-icon" />
        <p>Không tìm thấy bệnh phù hợp.</p>
      </div>
    );
  }

  return (
    <ul className="disease-list" role="list">
      {items.map((d) => (
        <li key={d.id}>
          <button
            type="button"
            className={`disease-item${selectedId === d.id ? " disease-item--active" : ""}`}
            onClick={() => onSelect(d.id)}
          >
            <div className="disease-item-name">{d.disease_name}</div>
            {d.disease_category && (
              <span className="disease-item-category">{d.disease_category}</span>
            )}
            {d.summary && (
              <p className="disease-item-summary">{d.summary}</p>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}

// ── Main Explorer ─────────────────────────────────────────────────────────────

export function KnowledgeExplorer() {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [items, setItems] = useState<DiseaseSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Debounce query input by 400 ms
  const handleQueryChange = useCallback((value: string) => {
    setQuery(value);
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      setDebouncedQuery(value);
      setOffset(0);
      setSelectedId(null);
    }, 400);
  }, []);

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  // Fetch disease list whenever query/offset changes
  useEffect(() => {
    setLoading(true);
    setError(null);
    listDiseases(debouncedQuery || null, PAGE_SIZE, offset)
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Không thể kết nối Knowledge Graph. Vui lòng thử lại."))
      .finally(() => setLoading(false));
  }, [debouncedQuery, offset]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  function handlePrev() {
    if (offset > 0) {
      setOffset((o) => Math.max(0, o - PAGE_SIZE));
      setSelectedId(null);
    }
  }

  function handleNext() {
    if (offset + PAGE_SIZE < total) {
      setOffset((o) => o + PAGE_SIZE);
      setSelectedId(null);
    }
  }

  function handleSelect(id: string) {
    setSelectedId(id);
  }

  function handleBack() {
    setSelectedId(null);
  }

  const showDetail = selectedId !== null;

  return (
    <div className="knowledge-shell">
      {/* ── Left pane: search + list ── */}
      <div className={`knowledge-list-pane${showDetail ? " knowledge-list-pane--hidden-mobile" : ""}`}>
        {/* Header */}
        <div className="knowledge-list-header">
          <h1 className="knowledge-title">
            <BookOpen size={20} />
            Tra cứu bệnh
          </h1>
          <p className="knowledge-subtitle">
            {total > 0 ? `${total.toLocaleString("vi-VN")} bệnh trong Knowledge Graph` : "Đang tải…"}
          </p>
        </div>

        {/* Search bar */}
        <div className="knowledge-search-bar">
          <Search size={15} className="knowledge-search-icon" />
          <input
            ref={inputRef}
            id="knowledge-search-input"
            type="search"
            className="knowledge-search-input"
            placeholder="Tìm kiếm theo tên bệnh…"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            autoComplete="off"
            aria-label="Tìm kiếm bệnh"
          />
          {query && (
            <button
              type="button"
              className="knowledge-search-clear"
              onClick={() => { handleQueryChange(""); inputRef.current?.focus(); }}
              aria-label="Xóa tìm kiếm"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Content */}
        {loading ? (
          <div className="knowledge-state-center">
            <Loader2 size={22} className="spin" />
            <span>Đang tải…</span>
          </div>
        ) : error ? (
          <div className="knowledge-state-center knowledge-state-error">
            <AlertCircle size={20} />
            <span>{error}</span>
            <button
              type="button"
              className="link-btn"
              onClick={() => {
                setLoading(true);
                setError(null);
                listDiseases(debouncedQuery || null, PAGE_SIZE, offset)
                  .then((res) => { setItems(res.items); setTotal(res.total); })
                  .catch(() => setError("Không thể kết nối Knowledge Graph."))
                  .finally(() => setLoading(false));
              }}
            >
              Thử lại
            </button>
          </div>
        ) : (
          <DiseaseList
            items={items}
            onSelect={handleSelect}
            selectedId={selectedId}
          />
        )}

        {/* Pagination */}
        {!loading && !error && totalPages > 1 && (
          <div className="knowledge-pagination">
            <button
              type="button"
              className="pagination-btn"
              onClick={handlePrev}
              disabled={offset === 0}
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
              onClick={handleNext}
              disabled={offset + PAGE_SIZE >= total}
              aria-label="Trang sau"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>

      {/* ── Right pane: disease detail ── */}
      {showDetail && (
        <div className="knowledge-detail-pane">
          <DiseaseDetailPanel diseaseId={selectedId!} onBack={handleBack} />
        </div>
      )}

      {/* ── Empty detail placeholder (desktop) ── */}
      {!showDetail && (
        <div className="knowledge-detail-pane knowledge-detail-placeholder">
          <BookOpen size={44} className="knowledge-placeholder-icon" />
          <p>Chọn một bệnh để xem chi tiết</p>
        </div>
      )}
    </div>
  );
}
