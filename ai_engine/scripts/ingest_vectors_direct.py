"""Direct Vector Ingestion — Nạp dữ liệu VietMedKG trực tiếp vào Qdrant.

Bypasses LightRAG's LLM entity-extraction pipeline. Only calls bge-m3 embedding.
Reads preprocessed_data.csv → converts each disease row to natural-language text
→ embeds with bge-m3 → stores directly in Qdrant via rag.chunks_vdb.upsert().

Estimated time: 15-40 minutes (embedding only, no LLM needed).

Usage:
    python -m ai_engine.scripts.ingest_vectors_direct
    python -m ai_engine.scripts.ingest_vectors_direct --file data/preprocessed_data.csv --batch-size 50
"""

import argparse
import asyncio
import csv
import hashlib
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_CSV = Path("data/preprocessed_data.csv")
FILE_PATH_TAG = "preprocessed_data.csv"


# ── CSV → Natural Language ────────────────────────────────────────────────────

def _safe(val) -> str:
    """Return stripped string or empty if NaN/None."""
    if val is None or (isinstance(val, float) and val != val):
        return ""
    return str(val).strip()


def row_to_text(row: dict) -> str:
    """Convert a preprocessed_data.csv row to a Vietnamese natural-language chunk."""
    name = _safe(row.get("disease_name"))
    if not name:
        return ""

    parts = [f"Bệnh: {name}."]

    field_map = [
        ("disease_description", "Mô tả"),
        ("disease_category",    "Loại bệnh"),
        ("disease_cause",       "Nguyên nhân gây bệnh"),
        ("disease_symptom",     "Triệu chứng"),
        ("check_method",        "Phương pháp kiểm tra"),
        ("people_easy_get",     "Đối tượng dễ mắc bệnh"),
        ("associated_disease",  "Bệnh liên quan"),
        ("cure_method",         "Phương pháp điều trị"),
        ("cure_department",     "Khoa điều trị"),
        ("cure_probability",    "Tỉ lệ chữa khỏi"),
        ("drug_recommend",      "Thuốc đề xuất"),
        ("drug_common",         "Thuốc phổ biến"),
        ("drug_detail",         "Thông tin thuốc"),
        ("nutrition_do_eat",    "Nên ăn"),
        ("nutrition_not_eat",   "Không nên ăn"),
        ("nutrition_recommend_eat", "Thực phẩm khuyến nghị"),
        ("disease_prevention",  "Cách phòng tránh"),
    ]

    for col, label in field_map:
        val = _safe(row.get(col))
        if val:
            parts.append(f"{label}: {val}.")

    return "\n".join(parts)


def chunk_id_from_text(text: str) -> str:
    """Generate a stable MD5 hash key for a text chunk (LightRAG convention)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ── CSV Loading ───────────────────────────────────────────────────────────────

def load_csv(csv_path: Path) -> list[dict]:
    """Load CSV and convert all rows to {chunk_id: chunk_data} entries."""
    chunks: list[dict] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row_to_text(row)
            if not text:
                continue
            cid = chunk_id_from_text(text)
            disease_name = _safe(row.get("disease_name", ""))
            chunks.append({
                "id":          cid,
                "content":     text,
                "full_doc_id": disease_name or cid,
                "file_path":   FILE_PATH_TAG,
            })

    logger.info("Loaded %d valid disease chunks from %s", len(chunks), csv_path.name)
    return chunks


# ── Direct Ingestion ──────────────────────────────────────────────────────────

async def ingest_direct(chunks: list[dict], batch_size: int = 50):
    """Insert chunks directly into LightRAG's chunks_vdb (Qdrant).

    Calls embedding_func (bge-m3) for each batch — NO LLM involved.
    """
    from ai_engine.services.lightrag_service import get_lightrag_instance

    logger.info("Initializing LightRAG (connecting to Qdrant & Neo4j)...")
    rag = await get_lightrag_instance()
    logger.info("LightRAG initialized. Target collection: chunks_vdb (Qdrant)")

    total = len(chunks)
    total_batches = (total + batch_size - 1) // batch_size
    success = 0
    failed = 0

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        batch_num = i // batch_size + 1

        # Build the dict format LightRAG's upsert() expects:
        # { chunk_id: { "content": ..., "full_doc_id": ..., "file_path": ... } }
        upsert_data = {
            c["id"]: {
                "content":     c["content"],
                "full_doc_id": c["full_doc_id"],
                "file_path":   c["file_path"],
            }
            for c in batch
        }

        try:
            logger.info(
                "Batch [%d/%d] — embedding + upserting %d chunks...",
                batch_num, total_batches, len(batch),
            )
            # This calls bge-m3 internally, then upserts to Qdrant. NO LLM.
            await rag.chunks_vdb.upsert(upsert_data)
            success += len(batch)
            logger.info("Batch [%d/%d] ✅  %d chunks inserted", batch_num, total_batches, len(batch))

        except Exception as e:
            failed += len(batch)
            logger.error("Batch [%d/%d] ❌ Failed: %s", batch_num, total_batches, e)

    logger.info("=" * 60)
    logger.info(
        "Ingestion complete — ✅ %d success | ❌ %d failed | total %d",
        success, failed, total,
    )
    logger.info("=" * 60)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Direct vector ingestion into Qdrant (no LLM, only bge-m3 embedding)"
    )
    parser.add_argument(
        "--file", type=str,
        default=str(DEFAULT_CSV),
        help=f"Path to preprocessed CSV (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Number of disease records per Qdrant upsert call (default: 50)",
    )
    args = parser.parse_args()

    csv_path = Path(args.file)
    if not csv_path.exists():
        logger.error("CSV file not found: %s", csv_path)
        sys.exit(1)

    chunks = load_csv(csv_path)
    if not chunks:
        logger.error("No valid data found in %s", csv_path)
        sys.exit(1)

    logger.info(
        "Starting DIRECT vector ingestion: %d chunks → Qdrant (batch_size=%d)",
        len(chunks), args.batch_size,
    )
    logger.info("Embedding model: bge-m3 (1024-dim) | NO LLM extraction!")

    asyncio.run(ingest_direct(chunks, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
