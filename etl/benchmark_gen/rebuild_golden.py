"""
rebuild_golden.py

Rebuilds golden_test_v2.json from 1hop.json + 2hop.json:
  - ENTITY-SET question types only (D2: exclude free-text/outlier answer types)
  - CARD_CAP = 20  (D3: max answer cardinality)
  - Stratified sample N ≈ 100, seed = 42  (D3)
  - Enriched fields: complexity, direction, regime, answer_cardinality  (D1)

Also produces:
  data/benchmark/kg_entities.txt   — entity vocab for fabrication scoring
  data/benchmark/golden_test_v2_stats.md — distribution summary
"""

import json
import logging
import random
from collections import Counter, defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
INPUT_1HOP = BASE_DIR / "benchmark" / "1hop.json"
INPUT_2HOP = BASE_DIR / "benchmark" / "2hop.json"
INPUT_TRIPLES = BASE_DIR / "benchmark" / "triples.json"
OUTPUT_JSON = BASE_DIR / "benchmark" / "golden_test_v2.json"
OUTPUT_STATS = BASE_DIR / "benchmark" / "golden_test_v2_stats.md"
OUTPUT_KG = BASE_DIR / "benchmark" / "kg_entities.txt"

CARD_CAP = 20
TARGET_N = 100
SEED = 42

# ── Question-type whitelist (answer = short entity list) ────────────────────
# Excluded (free-text answers): bệnh_đến_{mô_tả, cách_phòng_tránh, nguyên_nhân, thông_tin_về_thuốc}
# Excluded (outlier values):    bệnh_đến_{tỉ_lệ_chữa_khỏi, loại}, loại_đến_bệnh
# Excluded (free-text 2-hop):   phương_pháp_điều_trị_đến_nguyên_nhân, triệu_chứng_đến_tỉ_lệ_chữa_khỏi

ENTITY_SET_TYPES: frozenset[str] = frozenset({
    # 1-hop forward  (disease → property entity-list)
    "bệnh_đến_triệu_chứng",
    "bệnh_đến_đối_tượng_dễ_mắc_bệnh",
    "bệnh_đến_bệnh_đi_kèm",
    "bệnh_đến_khoa_điều_trị",
    "bệnh_đến_phương_pháp_điều_trị",
    "bệnh_đến_kiểm_tra",
    "bệnh_đến_thực_phẩm_nên_ăn",
    "bệnh_đến_thực_phẩm_không_nên_ăn",
    "bệnh_đến_món_ăn_được_đề_xuất",
    "bệnh_đến_thuốc_đề_xuất",
    "bệnh_đến_thuốc_phổ_biến",
    # 1-hop reverse  (property → disease name)
    "triệu_chứng_đến_bệnh",
    "đối_tượng_dễ_mắc_bệnh_đến_bệnh",
    "bệnh_đi_kèm_đến_bệnh",
    "khoa_điều_trị_đến_bệnh",
    "phương_pháp_điều_trị_đến_bệnh",
    "kiểm_tra_đến_bệnh",
    "thực_phẩm_nên_ăn_đến_bệnh",
    "thực_phẩm_không_nên_ăn_đến_bệnh",
    "món_ăn_được_đề_xuất_đến_bệnh",
    "thuốc_đề_xuất_đến_bệnh",
    "thuốc_phổ_biến_đến_bệnh",
    "cách_phòng_tránh_đến_bệnh",
    "nguyên_nhân_đến_bệnh",
    "mô_tả_đến_bệnh",
    # 2-hop chains  (all have entity-list answers)
    "bệnh_đi_kèm_đến_phương_pháp_điều_trị",
    "bệnh_đi_kèm_đến_thực_phẩm_không_nên_ăn",
    "bệnh_đi_kèm_đến_thực_phẩm_nên_ăn",
    "nguyên_nhân_đến_phương_pháp_điều_trị",
    "triệu_chứng_đến_món_ăn_được_đề_xuất",
    "triệu_chứng_đến_thực_phẩm_không_nên_ăn",
    "triệu_chứng_đến_thực_phẩm_nên_ăn",
})

# Relations in triples.json whose tails are comma-separated entity lists
KG_ENTITY_RELATIONS: frozenset[str] = frozenset({
    "disease_symptom", "people_easy_get", "associated_disease", "cure_department",
    "cure_method", "check_method", "nutrition_do_eat", "nutrition_not_eat",
    "nutrition_recommend_eat", "drug_recommend", "drug_common",
})


# ── Helpers ─────────────────────────────────────────────────────────────────

def _cardinality(answer: str) -> int:
    return len([x for x in answer.split("|") if x.strip()])


def _direction(question_type: str, hop: str) -> str:
    if hop == "2hop":
        return "chain"
    if question_type.startswith("bệnh_đến_"):
        return "forward"
    return "reverse"


def _regime(card: int) -> str:
    return "single" if card == 1 else "multi"


def _stratum(r: dict) -> str:
    return f"{r['complexity']}|{r['direction']}|{r['regime']}"


# ── Load & filter ────────────────────────────────────────────────────────────

def load_and_filter() -> list[dict]:
    records: list[dict] = []
    for path, hop_tag in [(INPUT_1HOP, "1hop"), (INPUT_2HOP, "2hop")]:
        with open(path, encoding="utf-8") as f:
            raw: list[dict] = json.load(f)
        log.info("Loaded %d records from %s", len(raw), path.name)
        for r in raw:
            qt = r.get("question_type", "")
            if qt not in ENTITY_SET_TYPES:
                continue
            ans = r.get("answer", "")
            card = _cardinality(ans)
            if card < 1 or card > CARD_CAP:
                continue
            direction = _direction(qt, hop_tag)
            records.append({
                "question": r["question"],
                "question_type": qt,
                "answer": ans,
                "complexity": hop_tag,
                "direction": direction,
                "regime": _regime(card),
                "answer_cardinality": card,
            })
    log.info("After entity-set filter + CARD_CAP=%d: %d records", CARD_CAP, len(records))
    return records


# ── Stratified sampler ───────────────────────────────────────────────────────

def stratified_sample(records: list[dict], n: int, seed: int) -> list[dict]:
    """Proportional stratified sample with min=1 per stratum."""
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_stratum[_stratum(r)].append(r)

    total = len(records)
    alloc: dict[str, int] = {}
    frac: dict[str, float] = {}
    for s, group in by_stratum.items():
        exact = n * len(group) / total
        alloc[s] = max(1, int(exact))
        frac[s] = exact - int(exact)

    assigned = sum(alloc.values())
    if assigned < n:
        for s in sorted(frac, key=lambda k: -frac[k])[: n - assigned]:
            alloc[s] += 1
    # Trim overshoots caused by min=1 forcing (remove from largest allocations)
    while sum(alloc.values()) > n:
        s = max((s for s, a in alloc.items() if a > 1), key=lambda k: alloc[k], default=None)
        if s is None:
            break
        alloc[s] -= 1

    rng = random.Random(seed)
    sampled: list[dict] = []
    for s in sorted(alloc):
        group = by_stratum[s]
        k = min(alloc[s], len(group))
        sampled.extend(rng.sample(group, k))

    rng.shuffle(sampled)
    log.info(
        "Sampled %d questions across %d strata: %s",
        len(sampled),
        len(alloc),
        {s: alloc[s] for s in sorted(alloc)},
    )
    return sampled


# ── KG entity vocabulary ─────────────────────────────────────────────────────

def build_kg_entities() -> set[str]:
    log.info("Building KG_ENTITIES from triples.json ...")
    entities: set[str] = set()
    with open(INPUT_TRIPLES, encoding="utf-8") as f:
        triples: list[dict] = json.load(f)
    for t in triples:
        header = t.get("header", "").strip()
        if header:
            entities.add(header)
        if t.get("relation", "") in KG_ENTITY_RELATIONS:
            for part in t.get("tail", "").split(","):
                part = part.strip()
                if part:
                    entities.add(part)
    log.info("KG_ENTITIES: %d entries", len(entities))
    return entities


# ── Stats report ─────────────────────────────────────────────────────────────

def write_stats(sampled: list[dict], path: Path) -> None:
    lines = ["# golden_test_v2 — distribution stats\n\n"]
    lines.append(f"**Total:** {len(sampled)}\n\n")

    def table(title: str, counter: Counter) -> None:
        lines.append(f"## {title}\n\n| key | count |\n|---|---|\n")
        for k, c in sorted(counter.items()):
            lines.append(f"| {k} | {c} |\n")
        lines.append("\n")

    table("Stratum (complexity × direction × regime)", Counter(_stratum(r) for r in sampled))
    table("question_type", Counter(r["question_type"] for r in sampled))
    table("regime", Counter(r["regime"] for r in sampled))
    table("answer_cardinality", Counter(r["answer_cardinality"] for r in sampled))

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    log.info("Stats written to %s", path)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    records = load_and_filter()
    sampled = stratified_sample(records, TARGET_N, SEED)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(sampled, f, ensure_ascii=False, indent=2)
    log.info("Written: %s", OUTPUT_JSON)

    write_stats(sampled, OUTPUT_STATS)

    entities = build_kg_entities()
    with open(OUTPUT_KG, "w", encoding="utf-8") as f:
        for e in sorted(entities):
            f.write(e + "\n")
    log.info("Written: %s (%d entities)", OUTPUT_KG, len(entities))


if __name__ == "__main__":
    main()
