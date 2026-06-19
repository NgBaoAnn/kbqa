"""
score_golden.py  —  Hallucination scorer for AegisHealth benchmark.

Reads a raw inference JSONL (one question-answer pair per line) and computes
entity-set metrics that show whether the system fabricates vs. correctly
recalls entities from VietMedKG.

Metric summary
--------------
Primary (D4):
  recall              — gold items found as substrings in system answer
  precision           — correct items / total structured mentions (see below)
  f1                  — harmonic mean of P / R
  fabrication_rate    — structured mentions NOT in KG vocab / total mentions
  off_answer_rate     — fraction of questions with zero extractable mentions

By regime:
  single  → EM (exact match of first extracted mention) + Hits@1
  multi   → set P / R / F1

Secondary (D6):  BERTScore (optional, requires bert-score library)

Mention extraction
------------------
"Structured mentions" are extracted deterministically from system answer
formatting markers: bold phrases (**x**), bullet/numbered list items,
pipe-separated sequences.  No LLM involvement.

These are used for precision and fabrication.  Recall is computed separately
by substring-checking each gold entity in the system answer text.

raw_*.jsonl schema (one JSON object per line):
    question, question_type, answer (gold, |-sep), complexity, direction,
    regime, answer_cardinality, system_answer, engine (opt), query_mode (opt),
    elapsed_ms (opt), error_code (null = success)

Usage (CLI):
    python -m ai_engine.eval.score_golden \\
        --raw  raw_hybrid.jsonl \\
        --gold data/benchmark/golden_test_v2.json \\
        --kg   data/benchmark/kg_entities.txt \\
        --out  results_hybrid.json [--bertscore]

Programmatic:
    from ai_engine.eval.score_golden import score_run
    report = score_run("raw_hybrid.jsonl", golden_path, kg_path)
"""

import argparse
import json
import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Text normalization ────────────────────────────────────────────────────────


def normalize(s: str) -> str:
    """Lowercase, strip, collapse whitespace, NFC. Preserves Vietnamese diacritics."""
    s = unicodedata.normalize("NFC", s).lower().strip()
    return re.sub(r"\s+", " ", s)


# ── Structured mention extraction ─────────────────────────────────────────────


def _extract_structured(text: str) -> list[str]:
    """Extract entity-candidate strings from system answer formatting.

    Targets: bold phrases (**...**), bullet/dash list items, numbered list
    items, pipe-separated sequences.  Filters out empty / over-long strings.
    """
    raw: list[str] = []

    # 1. Bold phrases: **phrase** (synthesizer marks entity names)
    for m in re.finditer(r"\*\*([^*\n]{1,80})\*\*", text):
        raw.append(m.group(1).strip())

    # 2. Bullet / dash list items
    for m in re.finditer(r"^[-•·]\s+(.{1,120})$", text, re.MULTILINE):
        raw.append(m.group(1).replace("**", "").rstrip(".,;").strip())

    # 3. Numbered list items  (1. / 1) / - 1.)
    for m in re.finditer(r"^\d+[.)]\s+(.{1,120})$", text, re.MULTILINE):
        raw.append(m.group(1).replace("**", "").rstrip(".,;").strip())

    # 4. Pipe-separated items (KG blob occasionally leaks through)
    if "|" in text:
        for part in text.split("|"):
            p = part.strip()
            if p:
                raw.append(p)

    # Deduplicate, filter by length
    seen: set[str] = set()
    result: list[str] = []
    for c in raw:
        c = c.strip()
        if not c or len(c) > 100:
            continue
        key = normalize(c)
        if key and key not in seen:
            seen.add(key)
            result.append(c)
    return result


# ── Per-question scorer ───────────────────────────────────────────────────────


def score_question(
    gold_list: list[str],
    system_text: str,
    kg_norms: set[str],
    regime: str,
) -> dict:
    """Score one question-answer pair.

    Returns
    -------
    dict with keys:
        precision, recall, f1          — entity-set metrics
        fabrication_rate               — fraction of mentions NOT in KG
        off_answer                     — 1 if system produced zero extractable mentions
        em, hits1                      — only meaningful for regime='single'
        n_gold, n_hits, n_mentions, n_fabricated
    """
    # ── Error / empty answer ──────────────────────────────────────────────
    if not system_text or not system_text.strip():
        return {
            "precision": 0.0, "recall": 0.0, "f1": 0.0,
            "em": 0, "hits1": 0,
            "fabrication_rate": 0.0, "off_answer": 1,
            "n_gold": len(gold_list), "n_hits": 0, "n_mentions": 0, "n_fabricated": 0,
        }

    norm_text = normalize(system_text)
    gold_norms = [normalize(g) for g in gold_list]
    gold_set = set(gold_norms)

    # ── Recall: gold items as substrings ──────────────────────────────────
    hit_flags = [1 if g and g in norm_text else 0 for g in gold_norms]
    n_hits = sum(hit_flags)
    recall = n_hits / len(gold_norms) if gold_norms else 0.0

    # ── Structured mentions → Precision + Fabrication ─────────────────────
    raw_cands = _extract_structured(system_text)
    norm_cands = [normalize(c) for c in raw_cands]

    # Filter out very short strings (noise)
    norm_cands = [c for c in norm_cands if len(c) >= 2]

    off_answer = 1 if not norm_cands else 0

    if norm_cands:
        n_correct = sum(1 for c in norm_cands if c in gold_set)
        n_fabricated = sum(1 for c in norm_cands if c not in kg_norms)
        precision = n_correct / len(norm_cands)
        fabrication_rate = n_fabricated / len(norm_cands)
    else:
        # No structured output extracted (e.g. baseline prose answer).
        # Use recall as precision proxy so F1 = recall; fabrication = undefined.
        n_correct = n_hits
        n_fabricated = 0
        precision = recall
        fabrication_rate = 0.0  # cannot assess from prose

    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # ── EM + Hits@1 (single regime) ───────────────────────────────────────
    em = hits1 = 0
    if regime == "single" and gold_norms:
        hits1 = hit_flags[0]
        em = 1 if (norm_cands and norm_cands[0] == gold_norms[0]) else 0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "em": em,
        "hits1": hits1,
        "fabrication_rate": round(fabrication_rate, 4),
        "off_answer": off_answer,
        "n_gold": len(gold_norms),
        "n_hits": n_hits,
        "n_mentions": len(norm_cands),
        "n_fabricated": n_fabricated,
    }


# ── Aggregate helpers ─────────────────────────────────────────────────────────


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _aggregate(rows: list[dict]) -> dict:
    """Compute mean metrics over a list of per-question score dicts."""
    if not rows:
        return {}

    def collect(key: str) -> list[float]:
        return [r[key] for r in rows if key in r]

    return {
        "n": len(rows),
        "precision": _mean(collect("precision")),
        "recall": _mean(collect("recall")),
        "f1": _mean(collect("f1")),
        "fabrication_rate": _mean(collect("fabrication_rate")),
        "off_answer_rate": _mean(collect("off_answer")),
        "em": _mean(collect("em")),
        "hits1": _mean(collect("hits1")),
    }


# ── Optional BERTScore ─────────────────────────────────────────────────────────


def _bertscore_batch(hypotheses: list[str], references: list[str]) -> list[float]:
    """Compute sentence-level BERTScore F1 for each (hyp, ref) pair.

    Returns a list of floats. Falls back to zeros if bert-score not available.
    """
    try:
        from bert_score import score as bscore  # type: ignore
        _, _, F = bscore(hypotheses, references, lang="others", verbose=False)
        return [float(f) for f in F]
    except ImportError:
        log.warning("bert-score not installed; BERTScore disabled.")
        return [0.0] * len(hypotheses)


# ── Main scoring entry point ──────────────────────────────────────────────────


def score_run(
    raw_jsonl: str | Path,
    golden_path: str | Path,
    kg_path: str | Path,
    use_bertscore: bool = False,
) -> dict:
    """Score a raw inference JSONL against the golden test set.

    Parameters
    ----------
    raw_jsonl   Path to raw_*.jsonl produced by an inference notebook.
    golden_path Path to golden_test_v2.json (used for metadata only; answer
                field should also be present in raw_jsonl rows).
    kg_path     Path to kg_entities.txt (one entity per line).
    use_bertscore  Whether to compute BERTScore (requires bert-score library).

    Returns
    -------
    dict with keys: summary, by_regime, by_complexity, by_type, rows
    """
    raw_jsonl = Path(raw_jsonl)
    kg_path = Path(kg_path)

    # ── Load KG vocab ─────────────────────────────────────────────────────
    with open(kg_path, encoding="utf-8") as f:
        kg_norms: set[str] = {normalize(line) for line in f if line.strip()}
    log.info("Loaded %d KG entities (normalized)", len(kg_norms))

    # ── Load raw inference rows ───────────────────────────────────────────
    raw_rows: list[dict] = []
    with open(raw_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                raw_rows.append(json.loads(line))
    log.info("Loaded %d raw rows from %s", len(raw_rows), raw_jsonl.name)

    # ── Score each row ────────────────────────────────────────────────────
    scored_rows: list[dict] = []
    bertscore_hyps: list[str] = []
    bertscore_refs: list[str] = []

    for row in raw_rows:
        gold_str = row.get("answer", "")
        gold_list = [g.strip() for g in gold_str.split("|") if g.strip()]
        regime = row.get("regime", "multi")

        # Treat error responses as empty
        error_code = row.get("error_code")
        system_text = "" if error_code else (row.get("system_answer") or "")

        metrics = score_question(gold_list, system_text, kg_norms, regime)

        scored_row = {
            "question": row.get("question", ""),
            "question_type": row.get("question_type", ""),
            "complexity": row.get("complexity", ""),
            "direction": row.get("direction", ""),
            "regime": regime,
            "answer_cardinality": row.get("answer_cardinality", len(gold_list)),
            "engine": row.get("engine"),
            "error_code": error_code,
            "elapsed_ms": row.get("elapsed_ms"),
            **metrics,
        }
        scored_rows.append(scored_row)

        if use_bertscore:
            ref = ", ".join(gold_list)
            bertscore_refs.append(ref)
            bertscore_hyps.append(system_text or "")

    # ── Optional BERTScore ────────────────────────────────────────────────
    if use_bertscore and bertscore_hyps:
        bs_scores = _bertscore_batch(bertscore_hyps, bertscore_refs)
        for row, bs in zip(scored_rows, bs_scores):
            row["bertscore_f1"] = round(bs, 4)
        log.info("BERTScore computed (mean=%.4f)", _mean(bs_scores))

    # ── Aggregate ─────────────────────────────────────────────────────────
    by_regime: dict[str, dict] = {}
    for regime in ("single", "multi"):
        subset = [r for r in scored_rows if r["regime"] == regime]
        by_regime[regime] = _aggregate(subset)

    by_complexity: dict[str, dict] = {}
    for hop in ("1hop", "2hop"):
        subset = [r for r in scored_rows if r["complexity"] == hop]
        by_complexity[hop] = _aggregate(subset)

    by_type: dict[str, dict] = {}
    type_groups: dict[str, list[dict]] = defaultdict(list)
    for r in scored_rows:
        type_groups[r["question_type"]].append(r)
    for qt, rows in sorted(type_groups.items()):
        by_type[qt] = _aggregate(rows)

    overall = _aggregate(scored_rows)
    error_count = sum(1 for r in scored_rows if r.get("error_code"))
    timeout_count = sum(1 for r in scored_rows if r.get("error_code") == "TIMEOUT")

    report = {
        "summary": {
            **overall,
            "total": len(scored_rows),
            "error_count": error_count,
            "timeout_count": timeout_count,
        },
        "by_regime": by_regime,
        "by_complexity": by_complexity,
        "by_type": by_type,
        "rows": scored_rows,
    }

    log.info(
        "Scoring done — F1=%.3f Precision=%.3f Recall=%.3f Fabrication=%.3f",
        overall.get("f1", 0),
        overall.get("precision", 0),
        overall.get("recall", 0),
        overall.get("fabrication_rate", 0),
    )
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

_DEFAULT_GOLD = (
    Path(__file__).resolve().parent.parent.parent
    / "data/benchmark/golden_test_v2.json"
)
_DEFAULT_KG = (
    Path(__file__).resolve().parent.parent.parent
    / "data/benchmark/kg_entities.txt"
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Score raw inference JSONL against golden set")
    parser.add_argument("--raw", required=True, type=Path, help="raw_*.jsonl inference file")
    parser.add_argument("--gold", type=Path, default=_DEFAULT_GOLD, help="golden_test_v2.json")
    parser.add_argument("--kg", type=Path, default=_DEFAULT_KG, help="kg_entities.txt")
    parser.add_argument("--out", type=Path, default=None, help="output results JSON")
    parser.add_argument("--bertscore", action="store_true", help="compute BERTScore (slow)")
    args = parser.parse_args()

    report = score_run(args.raw, args.gold, args.kg, use_bertscore=args.bertscore)

    s = report["summary"]
    print(f"\n{'='*55}")
    print(f"  SCORE REPORT  —  {args.raw.name}")
    print(f"{'='*55}")
    print(f"  Total:        {s['total']}  (errors: {s['error_count']}, timeouts: {s['timeout_count']})")
    print(f"  Precision:    {s['precision']:.3f}")
    print(f"  Recall:       {s['recall']:.3f}")
    print(f"  F1:           {s['f1']:.3f}")
    print(f"  Fabrication:  {s['fabrication_rate']:.3f}  ★")
    print(f"  Off-answer:   {s['off_answer_rate']:.3f}")
    print(f"\n  By regime:")
    for regime, m in report["by_regime"].items():
        if not m:
            continue
        em_str = f"  EM={m.get('em', 0):.3f}  Hits@1={m.get('hits1', 0):.3f}" if regime == "single" else ""
        print(f"    {regime:6s}  n={m.get('n',0):3d}  F1={m.get('f1',0):.3f}  Fab={m.get('fabrication_rate',0):.3f}{em_str}")
    print(f"{'='*55}\n")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"Results saved → {args.out}")


if __name__ == "__main__":
    main()
