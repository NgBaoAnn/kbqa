"""
Benchmark script for comparing SLM models on Text-to-Cypher task.
Task: M3-AI-01 — Benchmark 2–3 model SLM

Chỉ chạy queries và lưu kết quả thô.
Đánh giá accuracy sẽ được thực hiện riêng.

Usage:
    python ai-engine/eval/run_benchmark.py
    python ai-engine/eval/run_benchmark.py --models qwen2.5:3b llama3.2:3b
"""

import json
import time
import argparse
import subprocess
import re
from pathlib import Path
from datetime import datetime

try:
    from openai import OpenAI
except ImportError:
    print("❌ Missing dependency: pip install openai")
    exit(1)

# ─── Config ───────────────────────────────────────────────────────

OLLAMA_BASE_URL = "http://localhost:11434/v1"
PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "text_to_cypher.md"
QUESTIONS_FILE = Path(__file__).parent / "benchmark_questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

DEFAULT_MODELS = [
    "qwen2.5:3b",
    "llama3.2:3b",
]


# ─── Helpers ──────────────────────────────────────────────────────

def load_system_prompt() -> str:
    if not PROMPT_FILE.exists():
        print(f"❌ Prompt not found: {PROMPT_FILE}")
        exit(1)
    return PROMPT_FILE.read_text(encoding="utf-8")


def load_questions() -> list[dict]:
    if not QUESTIONS_FILE.exists():
        print(f"❌ Questions not found: {QUESTIONS_FILE}")
        exit(1)
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_vram_usage(model: str) -> str:
    try:
        result = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return "N/A"
        for line in result.stdout.strip().split("\n"):
            if model in line:
                m = re.search(r'(\d+\.?\d*)\s*(GB|MB|KB)', line)
                if m:
                    return f"{m.group(1)} {m.group(2)}"
        return "N/A"
    except Exception:
        return "N/A"


def get_processor_info(model: str) -> str:
    try:
        result = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return "N/A"
        for line in result.stdout.strip().split("\n"):
            if model in line:
                m = re.search(r'(\d+%\s*(?:GPU|CPU)[^\s]*)', line)
                if m:
                    return m.group(1)
        return "N/A"
    except Exception:
        return "N/A"


def query_model(client: OpenAI, model: str, system_prompt: str, question: str) -> tuple[str, float]:
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=256,
        )
        cypher = response.choices[0].message.content.strip()
        latency = (time.perf_counter() - start) * 1000
        return cypher, latency
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return f"ERROR: {e}", latency


# ─── Main ─────────────────────────────────────────────────────────

def run_benchmark(models: list[str]):
    system_prompt = load_system_prompt()
    questions = load_questions()
    client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = {}

    for model in models:
        print(f"\n{'='*60}")
        print(f"🤖 Model: {model}")
        print(f"{'='*60}")

        try:
            client.models.retrieve(model)
        except Exception:
            print(f"⚠️  Not found. Run: ollama pull {model}")
            continue

        # Warm up
        print(f"  ⏳ Warming up...")
        query_model(client, model, system_prompt, "What is diabetes?")

        vram = get_vram_usage(model)
        processor = get_processor_info(model)
        print(f"  💾 VRAM: {vram} | Processor: {processor}\n")

        results = []
        total_latency = 0.0

        for q in questions:
            generated, latency = query_model(client, model, system_prompt, q["question"])
            total_latency += latency

            results.append({
                "id": q["id"],
                "category": q["category"],
                "lang": q["lang"],
                "question": q["question"],
                "expected_cypher": q["expected_cypher"],
                "generated_cypher": generated,
                "latency_ms": round(latency, 1),
            })
            print(f"  Q{q['id']} [{q['category']}/{q['lang']}] ({latency:.0f}ms)")

        avg_latency = total_latency / len(questions) if questions else 0

        summary = {
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(questions),
            "avg_latency_ms": round(avg_latency, 1),
            "vram_usage": vram,
            "processor": processor,
            "results": results,
        }
        all_results[model] = summary

        print(f"\n  📊 Avg Latency: {avg_latency:.0f}ms | VRAM: {vram}")

        # Save per-model
        safe_name = model.replace(":", "_").replace("/", "_")
        out_file = RESULTS_DIR / f"benchmark_{safe_name}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  💾 Saved: {out_file}")

    # Comparison table
    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print("📊 SUMMARY")
        print(f"{'='*60}")
        print(f"{'Model':<25} {'Latency':>10} {'VRAM':>10} {'Processor':>12}")
        print("-" * 60)
        for model, s in all_results.items():
            print(f"{model:<25} {s['avg_latency_ms']:>8.0f}ms {s['vram_usage']:>10} {s['processor']:>12}")

    # Save comparison
    comp_file = RESULTS_DIR / "benchmark_comparison.json"
    comp = {m: {k: v for k, v in s.items() if k != "results"} for m, s in all_results.items()}
    with open(comp_file, "w", encoding="utf-8") as f:
        json.dump(comp, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Comparison: {comp_file}")
    print(f"\n👉 Kết quả đã lưu. Dùng agent để đánh giá accuracy từ các file JSON.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark SLM models on Text-to-Cypher")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="Models to benchmark")
    args = parser.parse_args()
    run_benchmark(args.models)
