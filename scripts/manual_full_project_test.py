"""Manual full-project smoke/integration test runner.

This script is intentionally black-box: it talks to the running frontend,
backend, and Supabase Auth exactly like a browser client would.

Prerequisites:
    1. Backend is running, for example:
       .venv/bin/python -m uvicorn api.app:app --app-dir src --host 127.0.0.1 --port 8000

    2. Frontend is running if frontend smoke is enabled, for example:
       cd frontend && npm run dev

Usage:
    .venv/bin/python scripts/manual_full_project_test.py

Useful options:
    .venv/bin/python scripts/manual_full_project_test.py --skip-frontend
    .venv/bin/python scripts/manual_full_project_test.py --api-base-url http://127.0.0.1:8000
    .venv/bin/python scripts/manual_full_project_test.py --frontend-base-url http://127.0.0.1:5173

Default manual accounts:
    user:  manual.user@example.com / ManualTest123!
    admin: manual.admin@example.com / ManualTest123!

Environment loaded, lowest to highest priority:
    .env, backend/.env, src/.env, frontend/.env
"""

from __future__ import annotations

import argparse
import asyncio
import html.parser
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ENV_FILES = [
    ROOT / ".env",
    ROOT / "backend" / ".env",
    ROOT / "src" / ".env",
    ROOT / "frontend" / ".env",
]

DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_FRONTEND_BASE_URL = "http://localhost:5173"
DEFAULT_USER_EMAIL = "manual.user@example.com"
DEFAULT_ADMIN_EMAIL = "manual.admin@example.com"
DEFAULT_PASSWORD = "ManualTest123!"

HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=240.0, write=30.0, pool=10.0)


@dataclass
class Check:
    name: str
    ok: bool
    status_code: int | None = None
    detail: str = ""
    duration_ms: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)


class AssetParser(html.parser.HTMLParser):
    """Collect Vite script/link assets from the frontend index HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "script" and attr.get("src"):
            self.assets.append(attr["src"] or "")
        if tag == "link" and attr.get("href") and attr.get("rel") in {"stylesheet", "modulepreload"}:
            self.assets.append(attr["href"] or "")


def load_env() -> list[str]:
    loaded: list[str] = []
    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(env_file, override=True)
            loaded.append(str(env_file.relative_to(ROOT)))
    return loaded


def auth_header(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def short_json(value: Any, limit: int = 360) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:limit]
    except Exception:
        return str(value)[:limit]


def require_keys(*keys: str) -> Callable[[Any], tuple[bool, str]]:
    def _validator(payload: Any) -> tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, "payload is not an object"
        missing = [key for key in keys if key not in payload]
        return not missing, f"missing keys: {missing}" if missing else ""

    return _validator


def nonempty_string_key(key: str) -> Callable[[Any], tuple[bool, str]]:
    def _validator(payload: Any) -> tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, "payload is not an object"
        value = payload.get(key)
        ok = isinstance(value, str) and bool(value.strip())
        return ok, f"{key} is empty" if not ok else ""

    return _validator


def chat_response_validator(
    *,
    expected_engine: str | None = None,
    persisted: bool | None = None,
) -> Callable[[Any], tuple[bool, str]]:
    def _validator(payload: Any) -> tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, "payload is not an object"
        for key in ("status", "answer", "sources", "safety", "metadata"):
            if key not in payload:
                return False, f"missing {key}"
        if payload.get("status") != "success":
            return False, f"status={payload.get('status')}"
        if not str(payload.get("answer") or "").strip():
            return False, "answer is empty"
        metadata = payload.get("metadata") or {}
        if expected_engine and metadata.get("engine") != expected_engine:
            return False, f"engine={metadata.get('engine')}, expected={expected_engine}"
        for key in ("engine", "query_mode", "execution_time_ms", "source_count"):
            if key not in metadata:
                return False, f"metadata missing {key}"
        for key in ("prompt_version", "model_name", "kg_version", "pipeline_version"):
            if key not in metadata:
                return False, f"metadata missing version field {key}"
        if persisted is not None and metadata.get("persisted") is not persisted:
            return False, f"metadata.persisted={metadata.get('persisted')}, expected={persisted}"
        return True, ""

    return _validator


async def login_supabase(
    client: httpx.AsyncClient,
    *,
    supabase_url: str,
    anon_key: str,
    email: str,
    password: str,
) -> tuple[Check, str | None]:
    started = time.monotonic()
    try:
        response = await client.post(
            f"{supabase_url.rstrip()}/auth/v1/token?grant_type=password",
            headers={
                "apikey": anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
        )
        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        ok = response.status_code == 200 and isinstance(token, str) and bool(token)
        detail = "" if ok else short_json(payload)
        return (
            Check(
                name=f"supabase-login:{email}",
                ok=ok,
                status_code=response.status_code,
                detail=detail,
                duration_ms=(time.monotonic() - started) * 1000,
                data={"user_id": (payload.get("user") or {}).get("id")} if isinstance(payload, dict) else {},
            ),
            token,
        )
    except Exception as exc:
        return (
            Check(
                name=f"supabase-login:{email}",
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
                duration_ms=(time.monotonic() - started) * 1000,
            ),
            None,
        )


async def request_check(
    client: httpx.AsyncClient,
    *,
    name: str,
    method: str,
    path: str,
    expected: set[int] = {200},
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    validator: Callable[[Any], tuple[bool, str]] | None = None,
) -> Check:
    started = time.monotonic()
    try:
        response = await client.request(
            method,
            path,
            headers=auth_header(token),
            json=json_body,
        )
        duration_ms = (time.monotonic() - started) * 1000
        payload: Any
        try:
            payload = response.json()
        except Exception:
            payload = response.text
        ok = response.status_code in expected
        detail = "" if ok else short_json(payload)
        data = payload if isinstance(payload, dict) else {}

        if ok and validator is not None:
            valid, reason = validator(payload)
            if not valid:
                ok = False
                detail = reason

        return Check(name, ok, response.status_code, detail, duration_ms, data)
    except Exception as exc:
        return Check(
            name,
            False,
            detail=f"{type(exc).__name__}: {exc}",
            duration_ms=(time.monotonic() - started) * 1000,
        )


async def stream_check(
    client: httpx.AsyncClient,
    *,
    conversation_id: str,
    token: str,
) -> Check:
    name = "api:conversation-message-stream"
    path = f"/api/v1/conversations/{conversation_id}/messages/stream"
    started = time.monotonic()
    events: list[str] = []
    final_payload: dict[str, Any] | None = None
    try:
        async with client.stream(
            "POST",
            path,
            headers=auth_header(token),
            json={
                "question": "Câu hỏi tổng quát về chăm sóc sức khỏe tim mạch?",
                "mode": "naive",
            },
        ) as response:
            current_event: str | None = None
            data_lines: list[str] = []
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    current_event = line.removeprefix("event:").strip()
                    events.append(current_event)
                    data_lines = []
                elif line.startswith("data:"):
                    data_lines.append(line.removeprefix("data:").strip())
                elif line == "" and current_event:
                    if current_event == "final" and data_lines:
                        final_payload = json.loads("\n".join(data_lines))
                    current_event = None
                    data_lines = []
                if final_payload is not None:
                    break

        required = {"stage", "sources", "metadata", "final"}
        ok = response.status_code == 200 and required.issubset(set(events)) and final_payload is not None
        detail = "" if ok else f"events={events}"
        if ok:
            valid, reason = chat_response_validator(expected_engine="lightrag", persisted=True)(final_payload)
            ok = valid
            detail = reason if not valid else ""
        return Check(
            name,
            ok,
            response.status_code,
            detail,
            (time.monotonic() - started) * 1000,
            {"events": events, "final_message_id": final_payload.get("message_id") if final_payload else None},
        )
    except Exception as exc:
        return Check(
            name,
            False,
            detail=f"{type(exc).__name__}: {exc}; events={events}",
            duration_ms=(time.monotonic() - started) * 1000,
        )


async def frontend_smoke(frontend_base_url: str) -> list[Check]:
    checks: list[Check] = []
    async with httpx.AsyncClient(base_url=frontend_base_url, timeout=HTTP_TIMEOUT) as client:
        started = time.monotonic()
        try:
            response = await client.get("/")
            html = response.text
            ok = response.status_code == 200 and "root" in html
            checks.append(
                Check(
                    "frontend:index",
                    ok,
                    response.status_code,
                    "" if ok else html[:300],
                    (time.monotonic() - started) * 1000,
                )
            )
            if ok:
                parser = AssetParser()
                parser.feed(html)
                for asset in parser.assets[:6]:
                    asset_started = time.monotonic()
                    asset_response = await client.get(asset)
                    asset_ok = asset_response.status_code == 200 and len(asset_response.content) > 0
                    checks.append(
                        Check(
                            f"frontend:asset:{asset}",
                            asset_ok,
                            asset_response.status_code,
                            "" if asset_ok else asset_response.text[:200],
                            (time.monotonic() - asset_started) * 1000,
                        )
                    )
        except Exception as exc:
            checks.append(Check("frontend:index", False, detail=f"{type(exc).__name__}: {exc}"))
    return checks


async def run_backend_suite(
    *,
    api_base_url: str,
    supabase_url: str,
    anon_key: str,
    user_email: str,
    user_password: str,
    admin_email: str,
    admin_password: str,
) -> list[Check]:
    checks: list[Check] = []

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as auth_client:
        user_login, user_token = await login_supabase(
            auth_client,
            supabase_url=supabase_url,
            anon_key=anon_key,
            email=user_email,
            password=user_password,
        )
        admin_login, admin_token = await login_supabase(
            auth_client,
            supabase_url=supabase_url,
            anon_key=anon_key,
            email=admin_email,
            password=admin_password,
        )
        checks.extend([user_login, admin_login])

    async with httpx.AsyncClient(base_url=api_base_url, timeout=HTTP_TIMEOUT) as client:
        public_checks = [
            ("api:root", "GET", "/", {200}, None, None, require_keys("name", "version", "engine")),
            ("api:docs", "GET", "/docs", {200}, None, None, None),
            ("api:redoc", "GET", "/redoc", {200}, None, None, None),
            ("api:openapi", "GET", "/openapi.json", {200}, None, None, require_keys("openapi", "info", "paths")),
            ("api:docs-oauth", "GET", "/docs/oauth2-redirect", {200}, None, None, None),
            ("api:health", "GET", "/health", {200}, None, None, require_keys("status", "services", "version")),
            ("api:v1-health", "GET", "/api/v1/health", {200}, None, None, require_keys("status", "services", "version")),
            ("api:graph-schema", "GET", "/health/graph-schema", {200}, None, None, None),
            ("api:v1-graph-schema", "GET", "/api/v1/health/graph-schema", {200}, None, None, None),
            ("api:schema", "GET", "/api/v1/schema", {200}, None, None, None),
            ("api:knowledge-list", "GET", "/api/v1/knowledge/diseases?limit=3", {200}, None, None, require_keys("items", "total", "limit", "offset")),
            ("api:knowledge-missing", "GET", "/api/v1/knowledge/diseases/__manual_missing__", {404}, None, None, None),
            ("api:me-unauth", "GET", "/api/v1/me", {401}, None, None, None),
            ("api:admin-metrics-unauth", "GET", "/api/v1/admin/metrics", {401}, None, None, None),
            ("api:feedback-unauth", "POST", "/api/v1/messages/not-a-message/feedback", {401}, None, {"rating": "up"}, None),
        ]
        for name, method, path, expected, token, body, validator in public_checks:
            checks.append(
                await request_check(
                    client,
                    name=name,
                    method=method,
                    path=path,
                    expected=expected,
                    token=token,
                    json_body=body,
                    validator=validator,
                )
            )

        disease_items = checks[-5].data.get("items") if isinstance(checks[-5].data, dict) else None
        if disease_items:
            disease_id = disease_items[0].get("id") or disease_items[0].get("disease_name")
            checks.append(
                await request_check(
                    client,
                    name="api:knowledge-detail",
                    method="GET",
                    path=f"/api/v1/knowledge/diseases/{disease_id}",
                    expected={200},
                    validator=require_keys("id", "disease_name"),
                )
            )

        if user_token:
            user_checks = [
                ("api:me-user", "GET", "/api/v1/me", {200}, user_token, None, require_keys("id", "email", "role", "auth_provider")),
                ("api:preferences-get", "GET", "/api/v1/me/preferences", {200}, user_token, None, require_keys("language", "explanation_level", "answer_style")),
                (
                    "api:preferences-patch",
                    "PATCH",
                    "/api/v1/me/preferences",
                    {200},
                    user_token,
                    {"language": "vi", "explanation_level": "general", "answer_style": "concise"},
                    require_keys("language", "explanation_level", "answer_style"),
                ),
                ("api:conversations-list", "GET", "/api/v1/conversations", {200}, user_token, None, None),
                ("api:admin-metrics-user-forbidden", "GET", "/api/v1/admin/metrics", {403}, user_token, None, None),
                ("api:admin-review-user-forbidden", "GET", "/api/v1/admin/review-items", {403}, user_token, None, None),
            ]
            for name, method, path, expected, token, body, validator in user_checks:
                checks.append(
                    await request_check(
                        client,
                        name=name,
                        method=method,
                        path=path,
                        expected=expected,
                        token=token,
                        json_body=body,
                        validator=validator,
                    )
                )

            checks.append(
                await request_check(
                    client,
                    name="api:query-cypher",
                    method="POST",
                    path="/api/v1/query",
                    expected={200},
                    token=user_token,
                    json_body={"question": "Bệnh tiểu đường có triệu chứng gì?"},
                    validator=chat_response_validator(expected_engine="cypher_direct", persisted=False),
                )
            )
            checks.append(
                await request_check(
                    client,
                    name="api:query-lightrag",
                    method="POST",
                    path="/api/v1/query",
                    expected={200},
                    token=user_token,
                    json_body={
                        "question": "Hãy giải thích ngắn gọn cách duy trì lối sống lành mạnh.",
                        "mode": "naive",
                    },
                    validator=chat_response_validator(expected_engine="lightrag", persisted=False),
                )
            )

            create = await request_check(
                client,
                name="api:conversation-create",
                method="POST",
                path="/api/v1/conversations",
                expected={201},
                token=user_token,
                json_body={"title": "Manual full project test", "language": "vi"},
                validator=require_keys("id", "title", "language"),
            )
            checks.append(create)
            conversation_id = create.data.get("id")

            if conversation_id:
                msg = await request_check(
                    client,
                    name="api:conversation-message",
                    method="POST",
                    path=f"/api/v1/conversations/{conversation_id}/messages",
                    expected={201},
                    token=user_token,
                    json_body={"question": "Bệnh tiểu đường có triệu chứng gì?"},
                    validator=chat_response_validator(expected_engine="cypher_direct", persisted=True),
                )
                checks.append(msg)
                message_id = msg.data.get("message_id")

                checks.append(await stream_check(client, conversation_id=conversation_id, token=user_token))
                checks.append(
                    await request_check(
                        client,
                        name="api:conversation-detail",
                        method="GET",
                        path=f"/api/v1/conversations/{conversation_id}",
                        expected={200},
                        token=user_token,
                        validator=require_keys("conversation", "messages"),
                    )
                )
                checks.append(
                    await request_check(
                        client,
                        name="api:conversation-export-markdown",
                        method="GET",
                        path=f"/api/v1/conversations/{conversation_id}/export?format=markdown",
                        expected={200},
                        token=user_token,
                    )
                )
                checks.append(
                    await request_check(
                        client,
                        name="api:conversation-export-pdf-not-implemented",
                        method="GET",
                        path=f"/api/v1/conversations/{conversation_id}/export?format=pdf",
                        expected={501},
                        token=user_token,
                    )
                )
                checks.append(
                    await request_check(
                        client,
                        name="api:conversation-missing",
                        method="GET",
                        path="/api/v1/conversations/00000000-0000-0000-0000-000000000000",
                        expected={404},
                        token=user_token,
                    )
                )

                if message_id:
                    checks.append(
                        await request_check(
                            client,
                            name="api:message-trace",
                            method="GET",
                            path=f"/api/v1/messages/{message_id}/trace",
                            expected={200},
                            token=user_token,
                            validator=require_keys("message_id", "version_metadata", "engine_metadata"),
                        )
                    )
                    checks.append(
                        await request_check(
                            client,
                            name="api:feedback-up",
                            method="POST",
                            path=f"/api/v1/messages/{message_id}/feedback",
                            expected={201},
                            token=user_token,
                            json_body={
                                "rating": "up",
                                "reason": "helpful",
                                "comment": "Manual full project test positive feedback.",
                            },
                            validator=require_keys("id", "message_id", "rating", "created_at"),
                        )
                    )
                    checks.append(
                        await request_check(
                            client,
                            name="api:feedback-down-review-item",
                            method="POST",
                            path=f"/api/v1/messages/{message_id}/feedback",
                            expected={201},
                            token=user_token,
                            json_body={
                                "rating": "down",
                                "reason": "incorrect",
                                "comment": "Manual full project test negative feedback.",
                            },
                            validator=require_keys("id", "message_id", "rating", "created_at"),
                        )
                    )
        else:
            checks.append(Check("api:user-auth-dependent-suite", False, detail="Skipped: user login failed"))

        if admin_token:
            checks.append(
                await request_check(
                    client,
                    name="api:me-admin",
                    method="GET",
                    path="/api/v1/me",
                    expected={200},
                    token=admin_token,
                    validator=require_keys("id", "email", "role", "auth_provider"),
                )
            )
            checks.append(
                await request_check(
                    client,
                    name="api:admin-metrics",
                    method="GET",
                    path="/api/v1/admin/metrics",
                    expected={200},
                    token=admin_token,
                    validator=require_keys("request_count", "average_latency_ms", "engine_usage", "pending_review_count"),
                )
            )
            checks.append(
                await request_check(
                    client,
                    name="api:admin-review-items",
                    method="GET",
                    path="/api/v1/admin/review-items?limit=5&offset=0",
                    expected={200},
                    token=admin_token,
                    validator=require_keys("items", "total", "limit", "offset"),
                )
            )
        else:
            checks.append(Check("api:admin-auth-dependent-suite", False, detail="Skipped: admin login failed"))

    return checks


def print_report(checks: list[Check]) -> None:
    passed = sum(1 for check in checks if check.ok)
    failed = len(checks) - passed

    print("\nManual Full Project Test Report")
    print("=" * 88)
    for check in checks:
        status = "PASS" if check.ok else "FAIL"
        code = "-" if check.status_code is None else str(check.status_code)
        duration = f"{check.duration_ms:8.0f}ms"
        suffix = f" :: {check.detail}" if check.detail else ""
        print(f"{status:4} {code:>4} {duration}  {check.name}{suffix}")

    print("=" * 88)
    print(f"TOTAL: {len(checks)} | PASS: {passed} | FAIL: {failed}")

    if failed:
        print("\nFailed checks:")
        for check in checks:
            if not check.ok:
                print(f"- {check.name}: HTTP {check.status_code}; {check.detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual full-project smoke/integration test runner.")
    parser.add_argument("--api-base-url", default=os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--frontend-base-url", default=os.getenv("FRONTEND_BASE_URL", DEFAULT_FRONTEND_BASE_URL))
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend index/asset smoke checks.")
    parser.add_argument("--user-email", default=os.getenv("MANUAL_USER_EMAIL", DEFAULT_USER_EMAIL))
    parser.add_argument("--user-password", default=os.getenv("MANUAL_USER_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--admin-email", default=os.getenv("MANUAL_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL))
    parser.add_argument("--admin-password", default=os.getenv("MANUAL_ADMIN_PASSWORD", DEFAULT_PASSWORD))
    return parser.parse_args()


async def async_main() -> int:
    loaded_env = load_env()
    args = parse_args()

    supabase_url = (
        os.getenv("SUPABASE_URL")
        or os.getenv("VITE_SUPABASE_URL")
        or ""
    ).rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY") or ""

    checks: list[Check] = []
    print("Loaded env files:", ", ".join(loaded_env) if loaded_env else "(none)")
    print(f"API base URL: {args.api_base_url}")
    print(f"Frontend base URL: {args.frontend_base_url if not args.skip_frontend else '(skipped)'}")
    print(f"Manual user: {args.user_email}")
    print(f"Manual admin: {args.admin_email}")

    if not supabase_url or not anon_key:
        checks.append(
            Check(
                "config:supabase",
                False,
                detail="Missing SUPABASE_URL/VITE_SUPABASE_URL or SUPABASE_ANON_KEY/VITE_SUPABASE_ANON_KEY.",
            )
        )
        print_report(checks)
        return 1

    if not args.skip_frontend:
        checks.extend(await frontend_smoke(args.frontend_base_url))

    checks.extend(
        await run_backend_suite(
            api_base_url=args.api_base_url.rstrip("/"),
            supabase_url=supabase_url,
            anon_key=anon_key,
            user_email=args.user_email,
            user_password=args.user_password,
            admin_email=args.admin_email,
            admin_password=args.admin_password,
        )
    )

    print_report(checks)
    return 0 if all(check.ok for check in checks) else 1


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
