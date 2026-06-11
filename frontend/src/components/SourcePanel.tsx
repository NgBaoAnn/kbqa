/**
 * SourcePanel — displays citation/source records attached to an assistant message.
 *
 * Features:
 *  - Collapsible panel triggered by a "Sources" badge button
 *  - Source type icon/label for each of the supported types
 *  - Snippet preview, rank badge, metadata expansion
 *  - Empty state: renders nothing (no UI crash)
 */

import { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp, Database, FileText, Link, Search, Layers } from "lucide-react";
import type { ChatSource } from "../types/api";

// ── Source type metadata ──────────────────────────────────────────────────────

interface SourceTypeMeta {
  label: string;
  icon: React.ReactNode;
  colorClass: string;
}

function getSourceTypeMeta(sourceType: string): SourceTypeMeta {
  switch (sourceType) {
    case "cypher":
      return { label: "Cypher Query", icon: <Database size={12} />, colorClass: "source-type--cypher" };
    case "neo4j":
      return { label: "Neo4j Graph", icon: <Layers size={12} />, colorClass: "source-type--neo4j" };
    case "lightrag_entity":
      return { label: "Entity", icon: <Search size={12} />, colorClass: "source-type--lightrag" };
    case "lightrag_relationship":
      return { label: "Relationship", icon: <Link size={12} />, colorClass: "source-type--lightrag" };
    case "lightrag_chunk":
      return { label: "Text Chunk", icon: <FileText size={12} />, colorClass: "source-type--lightrag" };
    case "document":
      return { label: "Tài liệu", icon: <BookOpen size={12} />, colorClass: "source-type--document" };
    default:
      return { label: "Nguồn khác", icon: <FileText size={12} />, colorClass: "source-type--other" };
  }
}

// ── Single source card ────────────────────────────────────────────────────────

function SourceCard({ source }: { source: ChatSource }) {
  const [expanded, setExpanded] = useState(false);
  const meta = getSourceTypeMeta(source.source_type);
  const hasMetadata = Object.keys(source.metadata ?? {}).length > 0;

  return (
    <div className="source-card">
      <div className="source-card-header">
        <span className={`source-type-badge ${meta.colorClass}`}>
          {meta.icon}
          {meta.label}
        </span>
        <span className="source-rank">#{source.rank}</span>
      </div>

      <div className="source-title">{source.title}</div>

      {source.snippet && (
        <div className="source-snippet">{source.snippet}</div>
      )}

      {hasMetadata && (
        <button
          type="button"
          className="source-expand-btn"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? "Ẩn metadata" : "Xem metadata"}
        </button>
      )}

      {expanded && hasMetadata && (
        <div className="source-metadata">
          {Object.entries(source.metadata).map(([key, value]) => (
            <div key={key} className="source-meta-row">
              <span className="source-meta-key">{key}</span>
              <span className="source-meta-value">
                {typeof value === "string" || typeof value === "number"
                  ? String(value)
                  : JSON.stringify(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Source panel ──────────────────────────────────────────────────────────────

interface SourcePanelProps {
  sources: ChatSource[];
  /** If true, panel starts open */
  defaultOpen?: boolean;
}

export function SourcePanel({ sources, defaultOpen = false }: SourcePanelProps) {
  const [open, setOpen] = useState(defaultOpen);

  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="source-panel">
      <button
        type="button"
        className="source-panel-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`${open ? "Đóng" : "Mở"} panel nguồn trích dẫn`}
      >
        <BookOpen size={13} />
        <span>
          {sources.length} nguồn{sources.length > 1 ? "" : ""}
        </span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>

      {open && (
        <div className="source-panel-body" role="list" aria-label="Danh sách nguồn trích dẫn">
          {sources.map((src) => (
            <div key={src.id} role="listitem">
              <SourceCard source={src} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
