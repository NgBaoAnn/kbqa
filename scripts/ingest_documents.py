"""Convert CSV medical data to natural language paragraphs and ingest into LightRAG.

Usage:
    python -m ai_engine.scripts.ingest_documents --file data/preprocessed_data.csv
"""

import argparse
import asyncio
import csv
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

SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv"}


def csv_row_to_text(row: dict) -> str:
    """Convert a single CSV row (disease record) to a natural language paragraph."""
    parts = []
    name = row.get("disease_name", "").strip()
    if not name:
        return ""

    parts.append(f"Bệnh: {name}.")

    if row.get("disease_category", "").strip():
        parts.append(f"Danh mục: {row['disease_category'].strip()}.")
    if row.get("disease_description", "").strip():
        parts.append(f"Mô tả: {row['disease_description'].strip()}.")
    if row.get("disease_cause", "").strip():
        parts.append(f"Nguyên nhân: {row['disease_cause'].strip()}.")
    if row.get("disease_symptom", "").strip():
        parts.append(f"Triệu chứng: {row['disease_symptom'].strip()}.")
    if row.get("check_method", "").strip():
        parts.append(f"Phương pháp chẩn đoán: {row['check_method'].strip()}.")
    if row.get("people_easy_get", "").strip():
        parts.append(f"Đối tượng dễ mắc: {row['people_easy_get'].strip()}.")
    if row.get("associated_disease", "").strip():
        parts.append(f"Bệnh liên quan: {row['associated_disease'].strip()}.")
    if row.get("cure_method", "").strip():
        parts.append(f"Phương pháp điều trị: {row['cure_method'].strip()}.")
    if row.get("cure_department", "").strip():
        parts.append(f"Khoa điều trị: {row['cure_department'].strip()}.")
    if row.get("cure_probability", "").strip():
        parts.append(f"Khả năng chữa khỏi: {row['cure_probability'].strip()}.")
    if row.get("drug_recommend", "").strip():
        parts.append(f"Thuốc khuyến nghị: {row['drug_recommend'].strip()}.")
    if row.get("drug_common", "").strip():
        parts.append(f"Thuốc phổ biến: {row['drug_common'].strip()}.")
    if row.get("drug_detail", "").strip():
        parts.append(f"Chi tiết thuốc: {row['drug_detail'].strip()}.")
    if row.get("nutrition_do_eat", "").strip():
        parts.append(f"Nên ăn: {row['nutrition_do_eat'].strip()}.")
    if row.get("nutrition_not_eat", "").strip():
        parts.append(f"Không nên ăn: {row['nutrition_not_eat'].strip()}.")
    if row.get("nutrition_recommend_eat", "").strip():
        parts.append(f"Thực phẩm khuyến nghị: {row['nutrition_recommend_eat'].strip()}.")
    if row.get("disease_prevention", "").strip():
        parts.append(f"Phòng ngừa: {row['disease_prevention'].strip()}.")

    return " ".join(parts)


def load_csv(filepath: Path) -> list[str]:
    """Load CSV and convert each row to a text paragraph."""
    texts = []
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = csv_row_to_text(row)
            if text:
                texts.append(text)
    logger.info("Loaded %d records from %s", len(texts), filepath.name)
    return texts


def load_text(filepath: Path) -> list[str]:
    """Load a plain text file, split by double newlines."""
    content = filepath.read_text(encoding="utf-8").strip()
    # Split into chunks of ~2000 chars to not overwhelm the LLM
    chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
    return chunks


def collect_texts(source: str) -> list[str]:
    """Collect text chunks from a file or directory."""
    p = Path(source)
    all_texts = []

    if p.is_file():
        files = [p]
    elif p.is_dir():
        files = sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS)
    else:
        logger.error("Path not found: %s", p)
        return []

    for filepath in files:
        logger.info("Reading: %s", filepath.name)
        if filepath.suffix.lower() == ".csv":
            all_texts.extend(load_csv(filepath))
        else:
            all_texts.extend(load_text(filepath))

    return all_texts


async def ingest(texts: list[str], batch_size: int = 10):
    """Ingest text chunks into LightRAG in batches."""
    from ai_engine.services.lightrag_service import get_lightrag_instance

    rag = await get_lightrag_instance()
    total = len(texts)
    success = 0
    failed = 0

    logger.info("Starting ingestion of %d text chunks (batch_size=%d)...", total, batch_size)

    for i in range(0, total, batch_size):
        batch = texts[i : i + batch_size]
        batch_text = "\n\n---\n\n".join(batch)
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        try:
            logger.info(
                "Batch [%d/%d] — inserting %d chunks (%d chars)...",
                batch_num, total_batches, len(batch), len(batch_text),
            )
            await rag.ainsert(batch_text)
            success += len(batch)
            logger.info("Batch [%d/%d] ✅ Done", batch_num, total_batches)
        except Exception as e:
            failed += len(batch)
            logger.error("Batch [%d/%d] ❌ Failed: %s", batch_num, total_batches, e)

    logger.info("=" * 60)
    logger.info("Ingestion complete: %d success, %d failed, %d total chunks", success, failed, total)
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into LightRAG")
    parser.add_argument("--dir", type=str, default="data/", help="Directory containing documents")
    parser.add_argument("--file", type=str, default=None, help="Single file to ingest")
    parser.add_argument("--batch-size", type=int, default=10, help="Records per batch (default: 10)")
    args = parser.parse_args()

    source = args.file if args.file else args.dir
    texts = collect_texts(source)

    if not texts:
        logger.error("No data found. Place .txt/.md/.csv files in the data/ directory.")
        sys.exit(1)

    logger.info("Total chunks to ingest: %d", len(texts))
    asyncio.run(ingest(texts, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
