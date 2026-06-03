#!/usr/bin/env python3
"""Index VietMedKG documents into LightRAG.

Usage:
    # Dry-run — preview document conversion without indexing
    python -m ai_engine.scripts.index_documents --csv data/data_translated.csv --dry-run

    # Full indexing
    python -m ai_engine.scripts.index_documents --csv data/data_translated.csv

    # Show CSV statistics only
    python -m ai_engine.scripts.index_documents --csv data/data_translated.csv --stats-only
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_engine.services.indexing_service import csv_to_documents, get_csv_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_indexing(csv_path: str, batch_size: int = 20) -> None:
    """Run the full indexing pipeline: CSV → Documents → LightRAG.

    Args:
        csv_path: Path to the VietMedKG CSV file.
        batch_size: Number of documents to insert per batch.
    """
    # Lazy import to avoid circular deps and allow dry-run without LightRAG
    from ai_engine.services.lightrag_service import get_lightrag_instance

    logger.info("=== LightRAG Indexing Pipeline ===")
    logger.info("CSV source: %s", csv_path)

    # Step 1: Convert CSV to documents
    logger.info("Step 1/3: Converting CSV to documents...")
    documents = csv_to_documents(csv_path)
    logger.info("Generated %d documents.", len(documents))

    # Step 2: Initialize LightRAG
    logger.info("Step 2/3: Initializing LightRAG instance...")
    rag = await get_lightrag_instance()
    logger.info("LightRAG initialized successfully.")

    # Step 3: Insert documents in batches
    logger.info(
        "Step 3/3: Inserting %d documents (batch_size=%d)...",
        len(documents),
        batch_size,
    )
    start_time = time.time()
    total_inserted = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(documents) + batch_size - 1) // batch_size

        logger.info(
            "  Batch %d/%d (%d documents)...",
            batch_num,
            total_batches,
            len(batch),
        )

        try:
            await rag.ainsert(batch)
            total_inserted += len(batch)
        except Exception as e:
            logger.error("  Batch %d failed: %s", batch_num, e)
            logger.info("  Continuing with next batch...")

    elapsed = time.time() - start_time
    logger.info("=== Indexing Complete ===")
    logger.info("  Documents inserted: %d / %d", total_inserted, len(documents))
    logger.info("  Total time: %.1f seconds", elapsed)
    logger.info(
        "  Average: %.2f seconds/document",
        elapsed / total_inserted if total_inserted else 0,
    )


def show_stats(csv_path: str) -> None:
    """Display CSV statistics."""
    stats = get_csv_stats(csv_path)
    print("\n=== VietMedKG CSV Statistics ===")
    print(f"  File: {stats['file']}")
    print(f"  Total rows: {stats['total_rows']}")
    print(f"  Total columns: {stats['total_columns']}")
    print(f"  Unique diseases: {stats['unique_diseases']}")
    print(f"  Columns: {stats['columns']}")
    if stats["missing_values"]:
        print("  Missing values:")
        for col, count in stats["missing_values"].items():
            pct = count / stats["total_rows"] * 100
            print(f"    - {col}: {count} ({pct:.1f}%)")
    else:
        print("  Missing values: None")
    print()


def preview_documents(csv_path: str, n: int = 3) -> None:
    """Preview the first N generated documents."""
    documents = csv_to_documents(csv_path)
    print(f"\n=== Document Preview (first {n} of {len(documents)}) ===\n")
    for i, doc in enumerate(documents[:n]):
        print(f"--- Document {i + 1} ---")
        print(doc)
        print()
    print(f"... and {len(documents) - n} more documents.\n")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Index VietMedKG documents into LightRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to the VietMedKG data_translated.csv file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview document conversion without indexing",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Show CSV statistics only",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Number of documents per indexing batch (default: 20)",
    )
    parser.add_argument(
        "--preview-count",
        type=int,
        default=3,
        help="Number of documents to preview in dry-run (default: 3)",
    )

    args = parser.parse_args()

    if args.stats_only:
        show_stats(args.csv)
        return

    if args.dry_run:
        show_stats(args.csv)
        preview_documents(args.csv, n=args.preview_count)
        return

    # Full indexing
    asyncio.run(run_indexing(args.csv, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
