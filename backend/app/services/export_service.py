"""Conversation export service for Markdown and PDF downloads."""

from __future__ import annotations

import json
import re
import textwrap
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import HTTPException, status

from app.database import SupabaseDatabase, get_database
from app.models.contracts import ChatSource, ConversationSummary, SafetyPayload
from app.services.chat_service import CONVERSATION_COLUMNS, MESSAGE_COLUMNS

ExportFormat = Literal["markdown", "pdf"]
DISCLAIMER = (
    "Thông tin trong hội thoại chỉ mang tính chất tham khảo, không thay thế "
    "chẩn đoán hoặc điều trị từ nhân viên y tế."
)


@dataclass(frozen=True)
class ExportedConversation:
    content: bytes
    media_type: str
    filename: str


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "CONVERSATION_NOT_FOUND",
            "message": "Conversation was not found.",
        },
    )


def _safe_filename(title: str, extension: str) -> str:
    base = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-._").lower()
    return f"{base or 'conversation'}.{extension}"


def _normalise_metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalise_safety(value: Any) -> SafetyPayload:
    if isinstance(value, dict):
        return SafetyPayload(**value)
    return SafetyPayload(disclaimer=DISCLAIMER)


def _source_from_row(row: dict[str, Any]) -> ChatSource:
    return ChatSource(
        id=str(row["id"]),
        source_type=row["source_type"],
        title=row["title"],
        snippet=row.get("snippet"),
        rank=int(row.get("rank") or 1),
        metadata=_normalise_metadata(row.get("metadata")),
    )


def _fetch_export_rows(
    db: SupabaseDatabase,
    user_id: str,
    conversation_id: str,
) -> tuple[ConversationSummary, list[dict[str, Any]], dict[str, list[ChatSource]]]:
    conversation = db.fetch_one(
        f"""
        select {CONVERSATION_COLUMNS}
        from public.conversations
        where id = %s
          and user_id = %s
        """,
        (conversation_id, user_id),
    )
    if conversation is None:
        raise _not_found()

    messages = db.fetch_all(
        f"""
        select {MESSAGE_COLUMNS}
        from public.messages
        where conversation_id = %s
        order by created_at asc
        """,
        (conversation_id,),
    )

    assistant_ids = [row["id"] for row in messages if row.get("role") == "assistant"]
    if not assistant_ids:
        return ConversationSummary(**conversation), messages, {}

    source_rows = db.fetch_all(
        """
        select
            id::text as id,
            message_id::text as message_id,
            source_type,
            title,
            snippet,
            metadata,
            rank
        from public.message_sources
        where message_id = any(%s::uuid[])
        order by message_id asc, rank asc
        """,
        (assistant_ids,),
    )

    sources_by_message: dict[str, list[ChatSource]] = {}
    for row in source_rows:
        sources_by_message.setdefault(str(row["message_id"]), []).append(_source_from_row(row))
    return ConversationSummary(**conversation), messages, sources_by_message


def _format_metadata_value(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    if isinstance(value, str | int | float | bool):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def render_markdown(
    conversation: ConversationSummary,
    messages: list[dict[str, Any]],
    sources_by_message: dict[str, list[ChatSource]],
) -> str:
    lines = [
        f"# {conversation.title}",
        "",
        f"- Conversation ID: `{conversation.id}`",
        f"- Exported at: `{datetime.now(UTC).isoformat()}`",
        "",
        "## Safety Disclaimer",
        "",
        DISCLAIMER,
        "",
        "## Conversation",
        "",
    ]

    for index, message in enumerate(messages, start=1):
        role = "User" if message["role"] == "user" else "Assistant"
        lines.extend(
            [
                f"### {index}. {role}",
                "",
                str(message.get("content") or ""),
                "",
            ]
        )

        if message["role"] != "assistant":
            continue

        safety = _normalise_safety(message.get("safety"))
        metadata = _normalise_metadata(message.get("metadata"))
        lines.extend(
            [
                f"Safety: `{safety.level}` - {safety.disclaimer}",
                "",
            ]
        )

        sources = sources_by_message.get(str(message["id"]), [])
        if sources:
            lines.extend(["#### Sources / Citations", ""])
            for source in sources:
                lines.append(
                    f"{source.rank}. **{source.title}** "
                    f"(`{source.source_type}`, `{source.id}`)"
                )
                if source.snippet:
                    lines.append(f"   - Snippet: {source.snippet}")
                if source.metadata:
                    lines.append(
                        f"   - Metadata: `{json.dumps(source.metadata, ensure_ascii=False)}`"
                    )
            lines.append("")

        version_keys = ("prompt_version", "model_name", "kg_version", "pipeline_version")
        if any(metadata.get(key) for key in version_keys):
            lines.extend(["#### Version Trace", ""])
            for key in version_keys:
                label = key.replace("_", " ").title()
                lines.append(f"- {label}: `{_format_metadata_value(metadata.get(key))}`")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _ascii_pdf_line(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _markdown_to_pdf(markdown: str) -> bytes:
    wrapped_lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip() or " "
        wrapped_lines.extend(textwrap.wrap(line, width=92) or [" "])

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    ]

    content_lines = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
    for line in wrapped_lines[:52]:
        content_lines.append(f"({_ascii_pdf_line(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("latin-1", "ignore")

    objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"
    )

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


async def export_conversation(
    *,
    user_id: str,
    conversation_id: str,
    export_format: ExportFormat,
    database: SupabaseDatabase | None = None,
) -> ExportedConversation:
    db = database or get_database()
    conversation, messages, sources_by_message = _fetch_export_rows(db, user_id, conversation_id)
    markdown = render_markdown(conversation, messages, sources_by_message)

    if export_format == "markdown":
        return ExportedConversation(
            content=markdown.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            filename=_safe_filename(conversation.title, "md"),
        )

    if export_format == "pdf":
        return ExportedConversation(
            content=_markdown_to_pdf(markdown),
            media_type="application/pdf",
            filename=_safe_filename(conversation.title, "pdf"),
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error_code": "INVALID_EXPORT_FORMAT",
            "message": "Export format must be markdown or pdf.",
        },
    )
