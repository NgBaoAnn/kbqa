"""Compare six QA benchmark queries against legacy and refactored backends.

Prerequisites:
    Legacy backend:
        PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

    Refactored backend:
        .venv/bin/python -m uvicorn api.app:app --app-dir src --host 127.0.0.1 --port 8000

Usage:
    .venv/bin/python scripts/benchmark_query_compare.py

The script logs in to Supabase for the new backend and treats the legacy
backend as source of truth for answer shape and relative latency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ENV_FILES = [
    ROOT / ".env",
    ROOT / "backend" / ".env",
    ROOT / "src" / ".env",
    ROOT / "frontend" / ".env",
]

DEFAULT_OLD_URL = "http://127.0.0.1:8001"
DEFAULT_NEW_URL = "http://127.0.0.1:8000"
DEFAULT_EMAIL = "manual.user@example.com"
DEFAULT_PASSWORD = "ManualTest123!"

TIMEOUT = httpx.Timeout(connect=10.0, read=320.0, write=30.0, pool=10.0)


@dataclass(frozen=True)
class BenchmarkCase:
    label: str
    path: str
    question: str
    mode: str | None
    expected_engine: str


@dataclass
class QueryResult:
    ok: bool
    status_code: int | None
    duration_ms: float
    payload: dict[str, Any]
    answer: str
    engine: str
    response_type: str
    query_mode: str
    error: str = ""

    @property
    def answer_len(self) -> int:
        return len(self.answer.strip())


CASES = [
    BenchmarkCase(
        "C1",
        "cypher",
        "Bệnh tiểu đường có triệu chứng gì?",
        None,
        "cypher_direct",
    ),
    BenchmarkCase(
        "C2",
        "cypher",
        "Điều trị bệnh cao huyết áp như thế nào?",
        None,
        "cypher_direct",
    ),
    BenchmarkCase(
        "C3",
        "cypher",
        "Thuốc điều trị viêm phổi là gì?",
        None,
        "cypher_direct",
    ),
    BenchmarkCase(
        "L1",
        "lightrag",
        "Hãy giải thích ngắn gọn cách duy trì lối sống lành mạnh.",
        "naive",
        "lightrag",
    ),
    BenchmarkCase(
        "L2",
        "lightrag",
        "Mối liên hệ giữa béo phì và bệnh tim mạch là gì?",
        "naive",
        "lightrag",
    ),
    BenchmarkCase(
        "L3",
        "lightrag",
        "Tôi nên làm gì để cải thiện chất lượng giấc ngủ?",
        "naive",
        "lightrag",
    ),
]


def load_env() -> None:
    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(env_file, override=True)


def short(value: Any, limit: int = 260) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return text[:limit]


async def login(client: httpx.AsyncClient, email: str, password: str) -> str:
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in env files.")

    response = await client.post(
        f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
    )
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if response.status_code != 200 or not token:
        raise RuntimeError(f"Supabase login failed: {response.status_code} {short(payload)}")
    return token


def metadata(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("metadata")
    return raw if isinstance(raw, dict) else {}


def extract_result(response: httpx.Response, duration_ms: float) -> QueryResult:
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    meta = metadata(payload)
    answer = str(payload.get("answer") or "")
    engine = str(meta.get("engine") or payload.get("engine") or "unknown")
    response_type = str(payload.get("response_type") or payload.get("type") or "")
    query_mode = str(meta.get("query_mode") or payload.get("query_mode") or "")
    ok = response.status_code == 200
    error = "" if ok else short(payload)
    return QueryResult(ok, response.status_code, duration_ms, payload, answer, engine, response_type, query_mode, error)


async def call_query(
    client: httpx.AsyncClient,
    base_url: str,
    case: BenchmarkCase,
    *,
    token: str | None,
) -> QueryResult:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.monotonic()
    try:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/v1/query",
            headers=headers,
            json={"question": case.question, "mode": case.mode},
        )
        duration_ms = (time.monotonic() - started) * 1000
        return extract_result(response, duration_ms)
    except Exception as exc:
        return QueryResult(False, None, (time.monotonic() - started) * 1000, {}, "", "unknown", "", "", f"{type(exc).__name__}: {exc}")


async def warmup_backend(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str | None,
) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        await client.get(f"{base_url.rstrip('/')}/api/v1/health", headers=headers)
    except Exception:
        pass


def validate_case(
    case: BenchmarkCase,
    old: QueryResult,
    new: QueryResult,
    *,
    perf_ratio_max: float,
    lightrag_min_length_ratio: float,
) -> list[str]:
    failures: list[str] = []
    if not old.ok:
        failures.append(f"legacy failed: {old.status_code} {old.error}")
    if not new.ok:
        failures.append(f"new failed: {new.status_code} {new.error}")
    if failures:
        return failures

    answer = new.answer.strip()
    if not answer or answer.lower() == "none":
        failures.append("new answer is empty/None")
    if new.engine != case.expected_engine:
        failures.append(f"new engine={new.engine}, expected={case.expected_engine}")
    if not new.response_type:
        failures.append("new response_type is empty")

    ratio = new.duration_ms / old.duration_ms if old.duration_ms > 0 else float("inf")
    if ratio > perf_ratio_max:
        failures.append(f"latency ratio {ratio:.2f}x > {perf_ratio_max:.2f}x")

    meta = metadata(new.payload)
    if case.path == "cypher":
        if not meta.get("cypher"):
            failures.append("new cypher metadata is empty")
        if "suggested_questions" not in new.payload:
            failures.append("new suggested_questions missing")
        if "sources" not in new.payload:
            failures.append("new sources missing")
    else:
        for key in ("prompt_version", "model_name", "kg_version", "pipeline_version"):
            if key not in meta:
                failures.append(f"new metadata missing {key}")
        old_len = max(old.answer_len, 1)
        if new.answer_len < old_len * lightrag_min_length_ratio:
            failures.append(
                f"LightRAG answer length {new.answer_len}/{old.answer_len} "
                f"< {lightrag_min_length_ratio:.2f} source-of-truth ratio"
            )

    return failures


def print_row(case: BenchmarkCase, old: QueryResult, new: QueryResult, failures: list[str]) -> None:
    ratio = new.duration_ms / old.duration_ms if old.duration_ms > 0 else float("inf")
    status = "PASS" if not failures else "FAIL"
    print(
        f"{case.label:<2} {case.path:<8} "
        f"old={old.duration_ms:>8.0f}ms new={new.duration_ms:>8.0f}ms ratio={ratio:>5.2f}x "
        f"old_len={old.answer_len:<4} new_len={new.answer_len:<4} "
        f"engine={new.engine:<13} type={new.response_type:<14} {status}"
    )
    if failures:
        for failure in failures:
            print(f"   - {failure}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-url", default=DEFAULT_OLD_URL)
    parser.add_argument("--new-url", default=DEFAULT_NEW_URL)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--perf-ratio-max", type=float, default=1.0)
    parser.add_argument("--lightrag-min-length-ratio", type=float, default=0.75)
    parser.add_argument("--skip-warmup", action="store_true")
    args = parser.parse_args()

    load_env()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        token = await login(client, args.email, args.password)
        if not args.skip_warmup:
            await warmup_backend(client, base_url=args.old_url, token=None)
            await warmup_backend(client, base_url=args.new_url, token=token)

        total_failures: list[str] = []
        old_total = 0.0
        new_total = 0.0
        lightrag_old_total = 0.0
        lightrag_new_total = 0.0
        lightrag_count = 0

        for case in CASES:
            old = await call_query(client, args.old_url, case, token=None)
            new = await call_query(client, args.new_url, case, token=token)
            failures = validate_case(
                case,
                old,
                new,
                perf_ratio_max=args.perf_ratio_max,
                lightrag_min_length_ratio=args.lightrag_min_length_ratio,
            )
            print_row(case, old, new, failures)
            total_failures.extend(f"{case.label}: {failure}" for failure in failures)
            old_total += old.duration_ms
            new_total += new.duration_ms
            if case.path == "lightrag":
                lightrag_old_total += old.duration_ms
                lightrag_new_total += new.duration_ms
                lightrag_count += 1

        print()
        print(f"TOTAL old={old_total:.0f}ms new={new_total:.0f}ms ratio={new_total / old_total if old_total else float('inf'):.2f}x")
        if lightrag_count:
            print(
                "LIGHTRAG "
                f"old_avg={lightrag_old_total / lightrag_count:.0f}ms "
                f"new_avg={lightrag_new_total / lightrag_count:.0f}ms "
                f"ratio={lightrag_new_total / lightrag_old_total if lightrag_old_total else float('inf'):.2f}x"
            )

        if total_failures:
            print("\nFailures:")
            for failure in total_failures:
                print(f"- {failure}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
