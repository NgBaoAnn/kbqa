"""Manual Prompt Testing Tool — Interactive and batch testing.

Tests LightRAG query pipeline with individual questions.
Supports both batch mode (from file) and interactive mode.

Usage:
    python -m ai_engine.eval.test_prompt                     # Interactive mode
    python -m ai_engine.eval.test_prompt --batch FILE        # Batch mode
    python -m ai_engine.eval.test_prompt --quick             # Quick 5-question test
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Quick test questions (Vietnamese)
QUICK_TEST_QUESTIONS = [
    "Bệnh tiểu đường có triệu chứng gì?",
    "Thuốc điều trị cao huyết áp là gì?",
    "Viêm phổi là gì?",
    "Tôi bị đau ngực dữ dội và khó thở",
    "So sánh bệnh cảm cúm và viêm phổi",
]


async def test_single_question(question: str, mode: str | None = None) -> dict:
    """Test a single question through the pipeline.

    Args:
        question: The question string to test.
        mode: Optional LightRAG query mode override.

    Returns:
        A result dict with status, response type, answer, engine, and latency.
    """
    from backend.app.services.pipeline import run_pipeline

    start = time.time()
    result = await run_pipeline(question=question, language="vi", mode=mode)
    elapsed = (time.time() - start) * 1000

    return {
        "question": question,
        "status": result.get("status"),
        "response_type": result.get("response_type"),
        "answer": result.get("answer", "")[:500],
        "engine": result.get("metadata", {}).get("engine"),
        "query_mode": result.get("metadata", {}).get("query_mode"),
        "latency_ms": round(elapsed, 1),
    }


def print_result(result: dict, index: int = 0) -> None:
    """Pretty-print a single test result.

    Args:
        result: Result dict from ``test_single_question``.
        index: Display index number.
    """
    status_icon = "✅" if result["status"] == "success" else "❌"
    print(f"\n{'─' * 60}")
    print(f"  [{index}] {status_icon} {result['question']}")
    print(f"  Type: {result['response_type']} | Engine: {result['engine']} | Mode: {result['query_mode']}")
    print(f"  Latency: {result['latency_ms']}ms")
    print(f"  Answer: {result['answer'][:300]}")
    if len(result["answer"]) > 300:
        print(f"  ... (truncated, total {len(result['answer'])} chars)")


async def run_batch(questions: list[str], mode: str | None = None) -> list[dict]:
    """Run a batch of questions.

    Args:
        questions: List of question strings.
        mode: Optional LightRAG query mode override.

    Returns:
        List of result dicts.
    """
    results = []
    for i, q in enumerate(questions):
        logger.info("Testing [%d/%d]: %s", i + 1, len(questions), q[:60])
        result = await test_single_question(q, mode=mode)
        results.append(result)
        print_result(result, i + 1)
    return results


async def interactive_mode(mode: str | None = None) -> None:
    """Run in interactive mode — enter questions one by one.

    Args:
        mode: Optional LightRAG query mode override.
    """
    print("\n🧪 AegisHealth Prompt Tester — Interactive Mode")
    print("Type a question and press Enter. Type 'quit' or 'q' to exit.\n")

    i = 0
    while True:
        try:
            question = input("❓ Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if question.lower() in ("quit", "q", "exit"):
            break
        if not question:
            continue

        i += 1
        result = await test_single_question(question, mode=mode)
        print_result(result, i)

    print("\n👋 Goodbye!")


def main() -> None:
    """CLI entry point for the prompt testing tool."""
    parser = argparse.ArgumentParser(description="Manual Prompt Testing Tool")
    parser.add_argument("--batch", type=Path, help="JSON file with list of questions")
    parser.add_argument("--quick", action="store_true", help="Run 5 quick test questions")
    parser.add_argument("--mode", type=str, default=None, help="Force LightRAG query mode")
    parser.add_argument("--output", type=Path, help="Save results to JSON file")
    args = parser.parse_args()

    if args.quick:
        results = asyncio.run(run_batch(QUICK_TEST_QUESTIONS, mode=args.mode))
    elif args.batch:
        with open(args.batch) as f:
            data = json.load(f)
        questions = [q if isinstance(q, str) else q.get("question", "") for q in data]
        results = asyncio.run(run_batch(questions, mode=args.mode))
    else:
        asyncio.run(interactive_mode(mode=args.mode))
        return

    # Summary
    success = sum(1 for r in results if r["status"] == "success")
    total = len(results)
    avg_latency = sum(r["latency_ms"] for r in results) / total if total else 0
    print(f"\n📊 Summary: {success}/{total} success ({round(success / total * 100, 1)}%)")
    print(f"   Avg latency: {round(avg_latency, 1)}ms")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"   Results saved to {args.output}")


if __name__ == "__main__":
    main()
