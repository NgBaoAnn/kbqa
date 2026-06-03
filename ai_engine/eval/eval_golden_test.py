"""Golden Test Set Evaluation — End-to-end pipeline benchmark.

Runs all questions from golden_test_set.json through the full pipeline
and reports accuracy, response type correctness, and latency statistics.

Usage:
    python -m ai_engine.eval.eval_golden_test [--test-set FILE] [--output FILE]
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

EVAL_DIR = Path(__file__).parent
DEFAULT_TEST_SET = EVAL_DIR / "golden_test_set.json"
DEFAULT_OUTPUT = EVAL_DIR / "results" / "golden_test_results.json"


def load_test_set(path: Path) -> list[dict]:
    """Load the golden test set JSON file."""
    with open(path) as f:
        data = json.load(f)
    logger.info("Loaded %d test questions from %s", len(data), path.name)
    return data


async def run_single_test(question_data: dict) -> dict:
    """Run a single test question through the pipeline.

    Args:
        question_data: A dict from the golden test set with keys
            ``id``, ``question``, ``category``, ``expected_response_type``, etc.

    Returns:
        A result dict containing pass/fail status, latency, and answer preview.
    """
    from backend.app.services.pipeline import run_pipeline

    question = question_data["question"]
    start = time.time()

    try:
        result = await run_pipeline(question=question, language="vi")
        elapsed_ms = (time.time() - start) * 1000

        # Evaluate
        status_ok = result.get("status") == "success"
        answer_ok = bool(result.get("answer", "").strip())
        type_ok = result.get("response_type") in ("table", "text", "warning")

        # Check expected response type if specified
        expected_type = question_data.get("expected_response_type")
        type_match = (expected_type is None) or (result.get("response_type") == expected_type)

        return {
            "id": question_data["id"],
            "question": question,
            "category": question_data.get("category", "unknown"),
            "status": "PASS" if (status_ok and answer_ok and type_ok) else "FAIL",
            "type_match": type_match,
            "response_type": result.get("response_type"),
            "expected_type": expected_type,
            "engine": result.get("metadata", {}).get("engine"),
            "latency_ms": round(elapsed_ms, 1),
            "answer_preview": result.get("answer", "")[:200],
            "error": None,
        }
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return {
            "id": question_data["id"],
            "question": question,
            "category": question_data.get("category", "unknown"),
            "status": "ERROR",
            "type_match": False,
            "response_type": None,
            "expected_type": question_data.get("expected_response_type"),
            "engine": None,
            "latency_ms": round(elapsed_ms, 1),
            "answer_preview": None,
            "error": str(e),
        }


async def run_all_tests(test_set: list[dict]) -> list[dict]:
    """Run all tests sequentially.

    Args:
        test_set: List of question dicts loaded from the golden test set.

    Returns:
        List of result dicts, one per question.
    """
    results = []
    for i, q in enumerate(test_set):
        logger.info("[%d/%d] Testing: %s", i + 1, len(test_set), q["question"][:60])
        result = await run_single_test(q)
        results.append(result)
        status_icon = "✅" if result["status"] == "PASS" else "❌"
        logger.info(
            "  %s %s (%.0fms, type=%s)",
            status_icon, result["status"], result["latency_ms"], result["response_type"],
        )
    return results


def generate_report(results: list[dict]) -> dict:
    """Generate a summary report from test results.

    Args:
        results: List of result dicts from ``run_all_tests``.

    Returns:
        A report dict with ``summary``, ``latency``, ``by_category``, and ``results``.
    """
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    type_matches = sum(1 for r in results if r["type_match"])

    latencies = sorted(r["latency_ms"] for r in results if r["latency_ms"] is not None)

    # Per-category breakdown
    categories: dict[str, dict[str, int]] = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r["status"] == "PASS":
            categories[cat]["passed"] += 1

    report = {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
            "type_match_rate": round(type_matches / total * 100, 1) if total else 0,
        },
        "latency": {
            "p50_ms": round(latencies[len(latencies) // 2], 1) if latencies else 0,
            "p95_ms": round(latencies[int(len(latencies) * 0.95)], 1) if latencies else 0,
            "max_ms": round(max(latencies), 1) if latencies else 0,
            "min_ms": round(min(latencies), 1) if latencies else 0,
        },
        "by_category": categories,
        "results": results,
    }
    return report


def print_report(report: dict) -> None:
    """Print a human-readable report to stdout."""
    s = report["summary"]
    print("\n" + "=" * 60)
    print("GOLDEN TEST SET — EVALUATION REPORT")
    print("=" * 60)
    print(
        f"Total: {s['total']} | Passed: {s['passed']} "
        f"| Failed: {s['failed']} | Errors: {s['errors']}"
    )
    print(f"Pass Rate: {s['pass_rate']}%")
    print(f"Type Match Rate: {s['type_match_rate']}%")
    print(
        f"\nLatency: P50={report['latency']['p50_ms']}ms  "
        f"P95={report['latency']['p95_ms']}ms  "
        f"Max={report['latency']['max_ms']}ms"
    )
    print("\nBy Category:")
    for cat, data in report["by_category"].items():
        pct = round(data["passed"] / data["total"] * 100, 1) if data["total"] else 0
        print(f"  {cat}: {data['passed']}/{data['total']} ({pct}%)")
    print("=" * 60)


def main() -> None:
    """CLI entry point for golden test evaluation."""
    parser = argparse.ArgumentParser(description="Run Golden Test Set evaluation")
    parser.add_argument(
        "--test-set", type=Path, default=DEFAULT_TEST_SET,
        help="Path to golden test set JSON",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="Output results JSON path",
    )
    args = parser.parse_args()

    test_set = load_test_set(args.test_set)
    results = asyncio.run(run_all_tests(test_set))
    report = generate_report(results)
    print_report(report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Results saved to %s", args.output)


if __name__ == "__main__":
    main()
