#!/usr/bin/env python3
"""Blind Benchmark Runner — AegisHealth KBQA.

Chạy toàn bộ 45 câu trong benchmark_blind.md, ghi kết quả ra file.

Cách dùng:
    python ai_engine/eval/run_benchmark.py
    python ai_engine/eval/run_benchmark.py --url http://localhost:8001 --out results.md
"""

import argparse
import json
import os
import sys
import time

# Clean up NO_PROXY / no_proxy to avoid httpx parsing bugs with IPv6 (like ::1)
for var in ("NO_PROXY", "no_proxy"):
    if var in os.environ:
        os.environ[var] = ",".join([p for p in os.environ[var].split(",") if "::" not in p])

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print("❌ Cần cài httpx: pip install httpx")
    sys.exit(1)

# ── Test case definition ───────────────────────────────────────────────────

@dataclass
class TestCase:
    id: str
    group: str
    question: str
    expected_engine: str             # "cypher_direct" | "lightrag" | "any"
    expected_query_type: str         # "symptoms" | "find_by_*" | "any" | ...
    expected_response_type: str      # "text" | "table" | "warning" | "any"
    expect_disclaimer: bool | None   # True / False / None (don't check)
    expect_no_crash: bool = True
    notes: str = ""

    # Filled in after run
    result: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0
    error: str = ""


# ── All 45 benchmark test cases ──────────────────────────────────────────

CASES: list[TestCase] = [
    # ── Group A: CYPHER Forward (paraphrase mới hoàn toàn) ───────────────
    TestCase("B1",  "A", "dấu hiệu nhận biết bệnh sởi là gì?",
             "cypher_direct", "symptoms", "any", None),
    TestCase("B2",  "A", "bệnh lao phổi thường biểu hiện ra sao?",
             "cypher_direct", "symptoms", "any", None),
    TestCase("B3",  "A", "uống thuốc gì để trị viêm họng?",
             "cypher_direct", "medicine", "any", None),
    TestCase("B4",  "A", "viêm dạ dày chữa bằng phương pháp nào?",
             "cypher_direct", "treatment", "any", None),
    TestCase("B5",  "A", "người bệnh gút nên tránh ăn gì?",
             "cypher_direct", "advice", "any", None),
    TestCase("B6",  "A", "làm thế nào để không bị mắc bệnh sốt xuất huyết?",
             "cypher_direct", "prevention", "any", None),
    TestCase("B7",  "A", "đau dây thần kinh tọa nên đến khoa nào để khám?",
             "cypher_direct", "department", "any", None),
    TestCase("B8",  "A", "cho tôi biết tất cả về bệnh hen suyễn",
             "cypher_direct", "profile", "any", None),
    TestCase("B9",  "A", "bệnh tiểu đường kéo theo những bệnh nào khác?",
             "cypher_direct", "linked_diseases", "any", None),

    # ── Group B: CYPHER Reverse ──────────────────────────────────────────
    TestCase("B10", "B", "tôi bị nhức đầu, chóng mặt, mờ mắt — có thể là bệnh gì?",
             "cypher_direct", "find_by_symptom", "any", None),
    TestCase("B11", "B", "thuốc Metformin thường được dùng để điều trị bệnh gì?",
             "cypher_direct", "find_by_medicine", "any", None),
    TestCase("B12", "B", "tránh ăn mỡ động vật thì phòng được bệnh gì?",
             "any", "any", "any", None,
             notes="acceptable: cypher_direct find_by_prevention OR lightrag"),
    TestCase("B13", "B", "rau cần tây ăn tốt cho bệnh gì?",
             "cypher_direct", "find_by_nutrition_eat", "any", None),
    TestCase("B14", "B", "bệnh nào không được phép ăn hải sản?",
             "cypher_direct", "find_by_nutrition_avoid", "any", None),

    # ── Group C: LightRAG semantic ────────────────────────────────────────
    TestCase("B15", "C", "tại sao phụ nữ sau sinh hay bị thiếu máu?",
             "lightrag", "any", "any", None),
    TestCase("B16", "C", "stress ảnh hưởng đến hệ tiêu hóa như thế nào?",
             "lightrag", "any", "any", None),
    TestCase("B17", "C", "trẻ em hay mắc những bệnh truyền nhiễm nào nhất?",
             "lightrag", "any", "any", None),
    TestCase("B18", "C", "bệnh mãn tính ảnh hưởng đến chất lượng cuộc sống thế nào?",
             "lightrag", "any", "any", None),
    TestCase("B19", "C", "tôi 60 tuổi, huyết áp thường xuyên cao, nên làm gì?",
             "lightrag", "any", "any", True,
             notes="câu tư vấn cá nhân → phải có disclaimer"),
    TestCase("B20", "C", "mối liên hệ giữa béo phì và tiểu đường type 2 là gì?",
             "lightrag", "any", "any", None),

    # ── Group D: Adversarial — dễ route nhầm ────────────────────────────
    TestCase("B21", "D", "bệnh gout",
             "cypher_direct", "profile", "any", None,
             notes="entity ngắn, không có verb"),
    TestCase("B22", "D", "tiểu đường và các biến chứng",
             "any", "any", "any", None,
             notes="acceptable: linked_diseases hoặc lightrag"),
    TestCase("B23", "D", "thuốc hạ áp",
             "any", "any", "any", None,
             notes="không đủ context, không crash là pass"),
    TestCase("B24", "D", "phòng bệnh",
             "any", "any", "any", None,
             notes="quá mơ hồ, không crash là pass"),
    TestCase("B25", "D", "viêm",
             "any", "any", "any", None,
             notes="entity quá ngắn, disambiguation hoặc lightrag đều ok"),
    TestCase("B26", "D", "bệnh tiểu đường có liên quan đến tim mạch không?",
             "cypher_direct", "linked_diseases", "any", None),
    TestCase("B27", "D", "cả nhà tôi đều bị cao huyết áp, tôi có bị không?",
             "lightrag", "any", "any", None,
             notes="câu hỏi di truyền cá nhân"),
    TestCase("B28", "D", "bệnh đái tháo đường type 2 kiêng ăn gì?",
             "cypher_direct", "advice", "any", None,
             notes="alias 'đái tháo đường' của 'tiểu đường'"),

    # ── Group E: Input kỳ lạ ────────────────────────────────────────────
    TestCase("B29", "E", "benh tieu duong co trieu chung gi",
             "any", "any", "any", None,
             notes="không dấu tiếng Việt"),
    TestCase("B30", "E", "DM type 2 symptoms",
             "any", "any", "any", None,
             notes="viết tắt tiếng Anh"),
    TestCase("B31", "E", "bp cao uong thuoc gi",
             "any", "any", "any", None,
             notes="viết tắt + không dấu"),
    TestCase("B32", "E", "bệnh ... là gì???",
             "any", "any", "any", None,
             notes="ký tự thừa, không crash là pass"),
    TestCase("B33", "E", "TIỂU ĐƯỜNG CÓ TRIỆU CHỨNG GÌ",
             "cypher_direct", "symptoms", "any", None,
             notes="viết hoa toàn bộ"),
    TestCase("B34", "E", "bệnh tim mạch vành là gì ạ?",
             "any", "profile", "any", None,
             notes="có 'ạ' lịch sự"),
    TestCase("B35", "E", "cho hỏi bệnh thận mạn tính chữa thế nào ạ?",
             "cypher_direct", "treatment", "any", None,
             notes="có 'cho hỏi' + 'ạ'"),

    # ── Group F: Answer quality ───────────────────────────────────────────
    TestCase("B36", "F", "bệnh viêm loét dạ dày có triệu chứng gì?",
             "cypher_direct", "symptoms", "any", None,
             notes="answer phải có: đau bụng / ợ chua / buồn nôn"),
    TestCase("B37", "F", "bệnh tăng huyết áp điều trị bằng thuốc gì?",
             "cypher_direct", "medicine", "any", None,
             notes="answer phải có ít nhất 1 tên thuốc cụ thể"),
    TestCase("B38", "F", "người bị suy thận nên ăn gì và kiêng gì?",
             "cypher_direct", "advice", "any", None,
             notes="answer phải có cả nên ăn và kiêng"),
    TestCase("B39", "F", "bệnh gout liên quan đến những bệnh gì?",
             "cypher_direct", "linked_diseases", "any", None,
             notes="phải liệt kê ít nhất 2 bệnh liên quan"),
    TestCase("B40", "F", "tôi bị sốt cao 40 độ, co giật",
             "any", "any", "warning", None,
             notes="emergency → response_type=warning bắt buộc"),

    # ── Group G: Disclaimer logic ─────────────────────────────────────────
    TestCase("B41", "G", "bệnh tiểu đường phòng ngừa bằng cách nào?",
             "cypher_direct", "prevention", "any", True,
             notes="prevention = cần disclaimer"),
    TestCase("B42", "G", "bao nhiêu loại bệnh có trong hệ thống?",
             "cypher_direct", "count", "any", False,
             notes="count = không disclaimer"),
    TestCase("B43", "G", "bệnh nào dùng thuốc Amoxicillin?",
             "cypher_direct", "find_by_medicine", "any", False,
             notes="reverse lookup = không disclaimer"),
    TestCase("B44", "G", "tôi bị đau đầu mỗi sáng, có thể bị gì?",
             "any", "any", "any", True,
             notes="LightRAG medical advice → cần disclaimer"),
    TestCase("B45", "G", "khoa nào điều trị bệnh tim mạch?",
             "cypher_direct", "department", "any", False,
             notes="department = không disclaimer"),
]


# ── Evaluator ──────────────────────────────────────────────────────────────

DISCLAIMER_MARKER = "[!NOTE]"


def evaluate(case: TestCase) -> dict[str, str]:
    """Return dict of check → PASS / FAIL / SKIP."""
    r = case.result
    meta = r.get("metadata", {})

    engine  = meta.get("engine", "")
    qmode   = meta.get("query_mode", "")
    rtype   = r.get("response_type", "")
    answer  = r.get("answer", "")
    status  = r.get("status", "")

    checks: dict[str, str] = {}

    # Engine check
    if case.expected_engine == "any":
        checks["engine"] = "SKIP"
    else:
        checks["engine"] = "PASS" if engine == case.expected_engine else "FAIL"

    # Query type (extracted from "cypher:template:TYPE" or "cypher:llm:TYPE")
    if case.expected_query_type == "any":
        checks["query_type"] = "SKIP"
    else:
        parts = qmode.split(":")
        detected_type = parts[-1] if len(parts) >= 3 else qmode
        checks["query_type"] = "PASS" if detected_type == case.expected_query_type else "FAIL"

    # Response type
    if case.expected_response_type == "any":
        checks["response_type"] = "SKIP"
    else:
        checks["response_type"] = "PASS" if rtype == case.expected_response_type else "FAIL"

    # No crash (got a parseable response with a known status)
    checks["no_crash"] = "PASS" if status in ("success", "error") and not case.error else "FAIL"

    # Has a non-trivial answer
    checks["has_answer"] = "PASS" if answer and len(answer.strip()) > 10 else "FAIL"

    # Disclaimer
    if case.expect_disclaimer is None:
        checks["disclaimer"] = "SKIP"
    elif case.expect_disclaimer:
        checks["disclaimer"] = "PASS" if DISCLAIMER_MARKER in answer else "FAIL"
    else:
        checks["disclaimer"] = "PASS" if DISCLAIMER_MARKER not in answer else "FAIL"

    return checks


def is_overall_pass(checks: dict[str, str]) -> bool:
    return all(v != "FAIL" for v in checks.values())


# ── Runner ─────────────────────────────────────────────────────────────────

def run_all(base_url: str, timeout: float = 60.0) -> list[TestCase]:
    client = httpx.Client(timeout=timeout)
    total = len(CASES)

    print(f"\n🚀 Running {total} benchmark cases against {base_url}")
    print("─" * 65)

    for i, case in enumerate(CASES, 1):
        label = f"[{i:02d}/{total}] {case.id}"
        sys.stdout.write(f"  {label}  {case.question[:50]}...")
        sys.stdout.flush()
        t0 = time.time()
        try:
            resp = client.post(
                f"{base_url}/api/v1/query",
                json={"question": case.question},
            )
            case.result = resp.json()
            case.elapsed_ms = (time.time() - t0) * 1000
            checks = evaluate(case)
            ok = "✅" if is_overall_pass(checks) else "❌"
            print(f" {ok} ({case.elapsed_ms:.0f}ms)")
        except Exception as e:
            case.error = str(e)
            case.elapsed_ms = (time.time() - t0) * 1000
            print(f" 💥 {e}")

    client.close()
    return CASES


# ── Report writer ──────────────────────────────────────────────────────────

def _esc(text: str, max_len: int = 58) -> str:
    return text.replace("|", "\\|").replace("\n", " ")[:max_len]


def _icon(v: str) -> str:
    return {"PASS": "✅", "FAIL": "❌", "SKIP": "—"}[v]


def write_report(cases: list[TestCase], out_path: Path) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────
    lines += [
        "# 📊 Benchmark Report — AegisHealth KBQA",
        f"> **Generated**: {now}  ",
        f"> **Total cases**: {len(cases)}",
        "",
    ]

    # ── Compute stats ────────────────────────────────────────────────────
    group_names = {
        "A": "Forward CYPHER (paraphrase mới)",
        "B": "Reverse CYPHER",
        "C": "LightRAG semantic",
        "D": "Adversarial / boundary",
        "E": "Input kỳ lạ / edge cases",
        "F": "Answer quality",
        "G": "Disclaimer logic",
    }
    group_stats: dict[str, dict] = {g: {"pass": 0, "fail": 0} for g in group_names}
    total_pass = total_fail = 0

    all_checks: dict[str, dict[str, str]] = {}
    for case in cases:
        if case.error:
            all_checks[case.id] = {"no_crash": "FAIL"}
            group_stats[case.group]["fail"] += 1
            total_fail += 1
        else:
            ch = evaluate(case)
            all_checks[case.id] = ch
            if is_overall_pass(ch):
                group_stats[case.group]["pass"] += 1
                total_pass += 1
            else:
                group_stats[case.group]["fail"] += 1
                total_fail += 1

    # ── Summary table ─────────────────────────────────────────────────────
    lines += [
        "## 📋 Tổng quan",
        "",
        "| Nhóm | Mô tả | Câu | ✅ Pass | ❌ Fail |",
        "|------|-------|-----|--------|--------|",
    ]
    for g, name in group_names.items():
        st = group_stats[g]
        total_g = st["pass"] + st["fail"]
        lines.append(f"| **{g}** | {name} | {total_g} | {st['pass']} | {st['fail']} |")
    lines += [
        f"| | **TỔNG** | **{len(cases)}** | **{total_pass}** | **{total_fail}** |",
        "",
        "---",
        "",
    ]

    # ── Per-group detail tables ───────────────────────────────────────────
    current_group = None
    for case in cases:
        if case.group != current_group:
            current_group = case.group
            lines += [
                f"## Group {case.group} — {group_names.get(case.group, '')}",
                "",
                "| ID | Câu hỏi | Engine | Query mode | **Response type** | ms | eng | qtype | rtype | ans | discl | Result |",
                "|----|---------|--------|------------|-------------------|----|-----|-------|-------|-----|-------|--------|",
            ]

        ch = all_checks.get(case.id, {})
        ok = "✅ PASS" if is_overall_pass(ch) else "❌ FAIL"

        if case.error:
            lines.append(
                f"| {case.id} | {_esc(case.question)} | 💥ERROR | — | — | {case.elapsed_ms:.0f} "
                f"| — | — | — | — | — | **{ok}** |"
            )
            continue

        meta   = case.result.get("metadata", {})
        engine = meta.get("engine", "—")
        qmode  = meta.get("query_mode", "—")
        rtype  = case.result.get("response_type", "—")
        answer = case.result.get("answer", "")

        lines.append(
            f"| {case.id} | {_esc(case.question)} "
            f"| `{engine}` | `{qmode}` | **`{rtype}`** "
            f"| {case.elapsed_ms:.0f} "
            f"| {_icon(ch.get('engine','SKIP'))} "
            f"| {_icon(ch.get('query_type','SKIP'))} "
            f"| {_icon(ch.get('response_type','SKIP'))} "
            f"| {_icon(ch.get('has_answer','FAIL'))} ({len(answer.strip())}c) "
            f"| {_icon(ch.get('disclaimer','SKIP'))} "
            f"| **{ok}** |"
        )

    lines += ["", "---", ""]

    # ── ❌ Failures detail ────────────────────────────────────────────────
    failures = [c for c in cases if not is_overall_pass(all_checks.get(c.id, {"no_crash": "FAIL"}))]
    if failures:
        lines += [f"## ❌ Failures ({len(failures)} câu)", ""]
        for case in failures:
            ch = all_checks.get(case.id, {})
            failed_checks = [k for k, v in ch.items() if v == "FAIL"]
            lines += [
                f"### {case.id} — {case.question}",
                f"- **Failed checks**: {', '.join(failed_checks)}",
            ]
            if case.error:
                lines.append(f"- **Error**: {case.error}")
            else:
                meta = case.result.get("metadata", {})
                lines += [
                    f"- **Got engine**: `{meta.get('engine','—')}` (expected: `{case.expected_engine}`)",
                    f"- **Got query_mode**: `{meta.get('query_mode','—')}`",
                    f"- **Got response_type**: `{case.result.get('response_type','—')}` (expected: `{case.expected_response_type}`)",
                    f"- **Notes**: {case.notes or '—'}",
                ]
            lines.append("")
        lines += ["---", ""]

    # ── Raw answers (full dump) ───────────────────────────────────────────
    lines += ["## 📝 Raw Answers (đầy đủ)", ""]
    for case in cases:
        ch  = all_checks.get(case.id, {})
        ok  = "✅" if is_overall_pass(ch) else "❌"
        lines += [
            f"### {case.id} {ok} — {case.question}",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| Group | {case.group} — {group_names.get(case.group,'')} |",
            f"| Expected engine | `{case.expected_engine}` |",
            f"| Expected query_type | `{case.expected_query_type}` |",
            f"| Expected response_type | `{case.expected_response_type}` |",
            f"| Expect disclaimer | {case.expect_disclaimer} |",
            f"| Notes | {case.notes or '—'} |",
        ]

        if case.error:
            lines += [f"| **Error** | {case.error} |", ""]
            continue

        meta   = case.result.get("metadata", {})
        answer = case.result.get("answer", "")
        rtype  = case.result.get("response_type", "—")

        lines += [
            f"| **engine** | `{meta.get('engine','—')}` |",
            f"| **query_mode** | `{meta.get('query_mode','—')}` |",
            f"| **response_type** | **`{rtype}`** |",
            f"| elapsed | {case.elapsed_ms:.0f}ms |",
            f"| answer length | {len(answer.strip())} chars |",
            "",
            f"**Answer:**",
            "",
            "```",
            answer.strip()[:1000] + ("…[truncated]" if len(answer.strip()) > 1000 else ""),
            "```",
            "",
        ]

    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'─'*65}")
    print(f"📄 Report saved → {out_path}")
    print(f"   ✅ {total_pass} pass  |  ❌ {total_fail} fail  |  Total: {len(cases)}")
    print(f"{'─'*65}\n")


# ── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AegisHealth KBQA Benchmark Runner")
    parser.add_argument(
        "--url", default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--out", default=None,
        help="Output file path (default: benchmark_results_<timestamp>.md)",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0,
        help="Per-request timeout in seconds (default: 60)",
    )
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.out) if args.out else (
        Path(__file__).parent / f"benchmark_results_{timestamp}.md"
    )

    cases = run_all(base_url=args.url, timeout=args.timeout)
    write_report(cases, out_path)


if __name__ == "__main__":
    main()
