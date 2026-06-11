"""Sprint 3 — Người 2: Hardening tests for knowledge and admin endpoints.

Coverage
--------
knowledge_service (unit — mocked Neo4j):
  S3-BE-01  list_diseases: search, no-query, empty results, pagination
  S3-BE-02  get_disease: found, 404 not found, field parsing (symptoms/treatments/medicines/advice)

GET /api/v1/knowledge/diseases (HTTP integration):
  - 200 with items/total/limit/offset shape
  - ?q= search param forwarded
  - No auth required

GET /api/v1/knowledge/diseases/{id} (HTTP integration):
  - 200 with full detail shape
  - 404 for unknown disease

analytics_service (unit — mocked DB):
  S3-BE-03  get_admin_metrics: request_count, latency, engine_usage, feedback_rate, pending_review
  S3-BE-04  get_review_queue: items, pagination, JOIN result mapping

GET /api/v1/admin/metrics (HTTP integration):
  - Admin auth required → 403 for non-admin
  - 200 shape correct

GET /api/v1/admin/review-items (HTTP integration):
  - Admin auth required → 403 for non-admin
  - 200 shape correct, pagination params

Error handling:
  - Neo4j unavailable → 503
  - DB unavailable → 503
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time as _time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api_gateway import dependencies
from app.main import app
from app.services import analytics_service, knowledge_service, user_service


# ════════════════════════════════════════════════════════════════════════════
# Auth helpers (same pattern as Sprint 2 tests)
# ════════════════════════════════════════════════════════════════════════════


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _make_token(secret: str, user_id: str, email: str, role: str = "authenticated") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "sub": user_id,
        "email": email,
        "role": role,
        "aud": "authenticated",
        "exp": int(_time.time()) + 3600,
    }
    enc_header = _b64url(json.dumps(header, separators=(",", ":")).encode())
    enc_claims = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{enc_header}.{enc_claims}".encode("ascii")
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{enc_header}.{enc_claims}.{_b64url(sig)}"


def _user_headers(user_id: str = "user-1", email: str = "u@example.com") -> dict:
    return {"Authorization": f"Bearer {_make_token('test-secret', user_id, email)}"}


def _admin_headers(user_id: str = "admin-1", email: str = "admin@example.com") -> dict:
    return {"Authorization": f"Bearer {_make_token('test-secret', user_id, email)}"}


# ════════════════════════════════════════════════════════════════════════════
# Fake DB for admin tests
# ════════════════════════════════════════════════════════════════════════════


class FakeAdminDB:
    """Minimal fake DB backing analytics_service queries."""

    def __init__(
        self,
        *,
        request_count: int = 10,
        avg_latency: float = 500.0,
        p95_latency: float = 1200.0,
        engine_rows: list[dict] | None = None,
        total_feedback: int = 5,
        negative_count: int = 1,
        pending_review: int = 2,
        review_rows: list[dict] | None = None,
    ) -> None:
        self._request_count = request_count
        self._avg_latency = avg_latency
        self._p95_latency = p95_latency
        self._engine_rows = engine_rows or [{"engine": "lightrag", "cnt": 7}, {"engine": "cypher_direct", "cnt": 3}]
        self._total_feedback = total_feedback
        self._negative_count = negative_count
        self._pending_review = pending_review
        self._review_rows = review_rows or []

    def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        q = " ".join(query.lower().split())

        if "percentile_cont" in q:
            return {
                "request_count": self._request_count,
                "average_latency_ms": self._avg_latency,
                "p95_latency_ms": self._p95_latency,
            }

        if "from public.feedback" in q and "count(*) filter" in q:
            return {
                "total_feedback": self._total_feedback,
                "negative_count": self._negative_count,
            }

        if "from public.review_items" in q and "status = 'pending'" in q:
            return {"pending_count": self._pending_review}

        if "from public.review_items" in q and "count(*)" in q:
            return {"total": len(self._review_rows)}

        return None

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        q = " ".join(query.lower().split())

        if "group by engine" in q:
            return self._engine_rows

        if "join public.feedback" in q and "join public.messages" in q:
            return self._review_rows

        return []

    def execute(self, query: str, params: tuple = ()) -> None:
        pass


# ════════════════════════════════════════════════════════════════════════════
# Fake profile DB for auth
# ════════════════════════════════════════════════════════════════════════════


class FakeProfileDB:
    def __init__(self, user_id: str, role: str = "user") -> None:
        self._profile = {
            "id": user_id,
            "display_name": "Test",
            "role": role,
            "is_active": True,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        return self._profile

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        return []

    def execute(self, query: str, params: tuple = ()) -> None:
        pass


# ════════════════════════════════════════════════════════════════════════════
# S3-BE-01 — knowledge_service.list_diseases (unit)
# ════════════════════════════════════════════════════════════════════════════


class TestListDiseasesService:
    @pytest.mark.asyncio
    async def test_no_query_returns_list(self):
        count_rows = [{"total": 3}]
        disease_rows = [
            {"disease_name": "Viêm phổi", "disease_category": "Hô hấp", "disease_description": "Mô tả."},
            {"disease_name": "Tiểu đường", "disease_category": "Nội tiết", "disease_description": None},
            {"disease_name": "Đau đầu", "disease_category": None, "disease_description": "Đau đầu phổ biến."},
        ]
        calls = iter([count_rows, disease_rows])

        async def _mock_execute(q, p=None):
            return next(calls)

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = _mock_execute
            result = await knowledge_service.list_diseases(q=None, limit=20, offset=0)

        assert result.total == 3
        assert len(result.items) == 3
        assert result.items[0].disease_name == "Viêm phổi"

    @pytest.mark.asyncio
    async def test_query_filters_by_name(self):
        count_rows = [{"total": 1}]
        disease_rows = [
            {"disease_name": "Tiểu đường", "disease_category": "Nội tiết", "disease_description": "Rối loạn glucose."},
        ]
        calls = iter([count_rows, disease_rows])

        async def _mock_execute(q, p=None):
            return next(calls)

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = _mock_execute
            result = await knowledge_service.list_diseases(q="tiểu đường", limit=20, offset=0)

        assert result.total == 1
        assert result.items[0].disease_name == "Tiểu đường"

    @pytest.mark.asyncio
    async def test_empty_results_returns_zero_total(self):
        count_rows = [{"total": 0}]
        disease_rows: list = []
        calls = iter([count_rows, disease_rows])

        async def _mock_execute(q, p=None):
            return next(calls)

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = _mock_execute
            result = await knowledge_service.list_diseases(q="xyz_notfound", limit=20, offset=0)

        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_summary_truncated_at_120_chars(self):
        long_desc = "A" * 200
        count_rows = [{"total": 1}]
        disease_rows = [{"disease_name": "X", "disease_category": None, "disease_description": long_desc}]
        calls = iter([count_rows, disease_rows])

        async def _mock_execute(q, p=None):
            return next(calls)

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = _mock_execute
            result = await knowledge_service.list_diseases(q=None, limit=20, offset=0)

        assert len(result.items[0].summary) <= 122  # 120 chars + ellipsis

    @pytest.mark.asyncio
    async def test_pagination_limit_offset_respected(self):
        count_rows = [{"total": 50}]
        disease_rows = [
            {"disease_name": f"Disease {i}", "disease_category": None, "disease_description": None}
            for i in range(5)
        ]
        calls = iter([count_rows, disease_rows])

        async def _mock_execute(q, p=None):
            return next(calls)

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = _mock_execute
            result = await knowledge_service.list_diseases(q=None, limit=5, offset=10)

        assert result.total == 50
        assert result.limit == 5
        assert result.offset == 10
        assert len(result.items) == 5

    @pytest.mark.asyncio
    async def test_graph_unavailable_raises_503(self):
        from fastapi import HTTPException

        async def _fail(q, p=None):
            raise ConnectionError("AuraDB unreachable")

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = _fail
            with pytest.raises(HTTPException) as exc_info:
                await knowledge_service.list_diseases(q=None, limit=20, offset=0)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error_code"] == "KNOWLEDGE_GRAPH_UNAVAILABLE"


# ════════════════════════════════════════════════════════════════════════════
# S3-BE-02 — knowledge_service.get_disease (unit)
# ════════════════════════════════════════════════════════════════════════════


class TestGetDiseaseService:
    @pytest.mark.asyncio
    async def test_found_disease_returns_full_detail(self):
        row = {
            "disease_name": "Tiểu đường",
            "disease_description": "Rối loạn chuyển hóa glucose.",
            "disease_category": "Nội tiết",
            "disease_cause": "Di truyền, lối sống",
            "disease_symptom": "Khát nước;Đi tiểu nhiều;Mệt mỏi",
            "check_method": "Xét nghiệm đường huyết",
            "people_easy_get": "Người béo phì",
            "cure_method": "Dùng thuốc;Tập thể dục",
            "cure_department": "Nội tiết",
            "cure_probability": "Kiểm soát được",
            "drug_common": "Metformin",
            "drug_recommend": "Theo bác sĩ",
            "drug_detail": None,
            "nutrition_do_eat": "Rau xanh",
            "nutrition_recommend_meal": "Ăn ít đường",
            "nutrition_not_eat": "Đường tinh",
            "disease_prevention": "Tập thể dục đều",
        }

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = AsyncMock(return_value=[row])
            result = await knowledge_service.get_disease(disease_id="Tiểu đường")

        assert result.disease_name == "Tiểu đường"
        assert result.description == "Rối loạn chuyển hóa glucose."
        assert "Khát nước" in result.symptoms
        assert "Đi tiểu nhiều" in result.symptoms
        assert "Mệt mỏi" in result.symptoms
        assert "Metformin" in result.medicines
        assert len(result.advice) > 0

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self):
        from fastapi import HTTPException

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = AsyncMock(return_value=[])
            with pytest.raises(HTTPException) as exc_info:
                await knowledge_service.get_disease(disease_id="NonExistentDisease")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error_code"] == "DISEASE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_null_fields_produce_empty_lists(self):
        row: dict[str, Any] = {
            "disease_name": "Bệnh X",
            "disease_description": None,
            "disease_category": None,
            "disease_cause": None,
            "disease_symptom": None,
            "check_method": None,
            "people_easy_get": None,
            "cure_method": None,
            "cure_department": None,
            "cure_probability": None,
            "drug_common": None,
            "drug_recommend": None,
            "drug_detail": None,
            "nutrition_do_eat": None,
            "nutrition_recommend_meal": None,
            "nutrition_not_eat": None,
            "disease_prevention": None,
        }

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = AsyncMock(return_value=[row])
            result = await knowledge_service.get_disease(disease_id="Bệnh X")

        assert result.symptoms == []
        assert result.treatments == []
        assert result.medicines == []
        assert result.advice == []

    @pytest.mark.asyncio
    async def test_medicine_deduplication(self):
        row: dict[str, Any] = {
            "disease_name": "Bệnh Y",
            "disease_description": None,
            "disease_category": None,
            "disease_cause": None,
            "disease_symptom": None,
            "check_method": None,
            "people_easy_get": None,
            "cure_method": None,
            "cure_department": None,
            "cure_probability": None,
            "drug_common": "Paracetamol",
            "drug_recommend": "Paracetamol",  # duplicate
            "drug_detail": "Paracetamol 500mg",  # different
            "nutrition_do_eat": None,
            "nutrition_recommend_meal": None,
            "nutrition_not_eat": None,
            "disease_prevention": None,
        }

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = AsyncMock(return_value=[row])
            result = await knowledge_service.get_disease(disease_id="Bệnh Y")

        # Paracetamol should appear only once despite being in drug_common and drug_recommend
        assert result.medicines.count("Paracetamol") == 1

    @pytest.mark.asyncio
    async def test_graph_unavailable_raises_503(self):
        from fastapi import HTTPException

        with patch("app.services.knowledge_service.graph_service") as mock_gs:
            mock_gs.execute_cypher = AsyncMock(side_effect=Exception("Neo4j down"))
            with pytest.raises(HTTPException) as exc_info:
                await knowledge_service.get_disease(disease_id="X")

        assert exc_info.value.status_code == 503


# ════════════════════════════════════════════════════════════════════════════
# S3-BE-03 — analytics_service.get_admin_metrics (unit)
# ════════════════════════════════════════════════════════════════════════════


class TestAdminMetricsService:
    @pytest.mark.asyncio
    async def test_returns_correct_request_count(self):
        fake_db = FakeAdminDB(request_count=42)
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_admin_metrics()
        assert result.request_count == 42

    @pytest.mark.asyncio
    async def test_returns_correct_latency(self):
        fake_db = FakeAdminDB(avg_latency=750.0, p95_latency=2500.0)
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_admin_metrics()
        assert result.average_latency_ms == 750.0
        assert result.p95_latency_ms == 2500.0

    @pytest.mark.asyncio
    async def test_engine_usage_aggregated(self):
        fake_db = FakeAdminDB(
            engine_rows=[
                {"engine": "lightrag", "cnt": 60},
                {"engine": "cypher_direct", "cnt": 40},
            ]
        )
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_admin_metrics()
        assert result.engine_usage["lightrag"] == 60
        assert result.engine_usage["cypher_direct"] == 40

    @pytest.mark.asyncio
    async def test_negative_feedback_rate_calculated(self):
        fake_db = FakeAdminDB(total_feedback=10, negative_count=2)
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_admin_metrics()
        assert result.negative_feedback_rate == pytest.approx(0.2, abs=1e-4)

    @pytest.mark.asyncio
    async def test_negative_feedback_rate_zero_when_no_feedback(self):
        fake_db = FakeAdminDB(total_feedback=0, negative_count=0)
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_admin_metrics()
        assert result.negative_feedback_rate == 0.0

    @pytest.mark.asyncio
    async def test_pending_review_count(self):
        fake_db = FakeAdminDB(pending_review=5)
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_admin_metrics()
        assert result.pending_review_count == 5

    @pytest.mark.asyncio
    async def test_db_unavailable_raises_503(self):
        from fastapi import HTTPException

        bad_db = MagicMock()
        bad_db.fetch_one.side_effect = Exception("connection refused")

        with patch("app.services.analytics_service.get_database", return_value=bad_db):
            with pytest.raises(HTTPException) as exc_info:
                await analytics_service.get_admin_metrics()
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error_code"] == "ANALYTICS_UNAVAILABLE"


# ════════════════════════════════════════════════════════════════════════════
# S3-BE-04 — analytics_service.get_review_queue (unit)
# ════════════════════════════════════════════════════════════════════════════


_SAMPLE_REVIEW_ROW = {
    "review_item_id": str(uuid4()),
    "status": "pending",
    "category": "answer_quality",
    "created_at": "2026-06-11T10:00:00+00:00",
    "feedback_id": str(uuid4()),
    "message_id": str(uuid4()),
    "rating": "down",
    "reason": "incorrect",
    "comment": "Missing info.",
    "conversation_id": str(uuid4()),
}


class TestReviewQueueService:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self):
        fake_db = FakeAdminDB(review_rows=[_SAMPLE_REVIEW_ROW])
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_review_queue(limit=20, offset=0)

        assert result.total == 1
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_item_fields_mapped_correctly(self):
        fake_db = FakeAdminDB(review_rows=[_SAMPLE_REVIEW_ROW])
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_review_queue(limit=20, offset=0)

        item = result.items[0]
        assert item.status == "pending"
        assert item.category == "answer_quality"
        assert item.rating == "down"
        assert item.reason == "incorrect"

    @pytest.mark.asyncio
    async def test_empty_queue_returns_zero_items(self):
        fake_db = FakeAdminDB(review_rows=[])
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_review_queue(limit=20, offset=0)

        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_pagination_fields_returned(self):
        fake_db = FakeAdminDB(review_rows=[_SAMPLE_REVIEW_ROW])
        with patch("app.services.analytics_service.get_database", return_value=fake_db):
            result = await analytics_service.get_review_queue(limit=5, offset=10)

        assert result.limit == 5
        assert result.offset == 10

    @pytest.mark.asyncio
    async def test_db_unavailable_raises_503(self):
        from fastapi import HTTPException

        bad_db = MagicMock()
        bad_db.fetch_one.side_effect = Exception("DB down")

        with patch("app.services.analytics_service.get_database", return_value=bad_db):
            with pytest.raises(HTTPException) as exc_info:
                await analytics_service.get_review_queue(limit=20, offset=0)
        assert exc_info.value.status_code == 503


# ════════════════════════════════════════════════════════════════════════════
# HTTP integration tests
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def client_user(monkeypatch):
    """TestClient with a normal user profile."""
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setattr(
        user_service,
        "get_database",
        lambda: FakeProfileDB("user-1", role="user"),
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_admin(monkeypatch):
    """TestClient with an admin user profile."""
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setattr(
        user_service,
        "get_database",
        lambda: FakeProfileDB("admin-1", role="admin"),
    )
    return TestClient(app, raise_server_exceptions=False)


class TestKnowledgeEndpoints:
    def _disease_list_return(self, items: list | None = None):
        from app.models.contracts import DiseaseListResponse, DiseaseSummary
        items = items or [
            DiseaseSummary(id="Viêm phổi", disease_name="Viêm phổi", disease_category="Hô hấp", summary="Mô tả."),
        ]
        return DiseaseListResponse(items=items, total=len(items), limit=20, offset=0)

    def _disease_detail_return(self):
        from app.models.contracts import DiseaseDetailResponse
        return DiseaseDetailResponse(
            id="Viêm phổi",
            disease_name="Viêm phổi",
            description="Viêm phổi là bệnh nhiễm trùng phổi.",
            symptoms=["Sốt", "Ho"],
            treatments=["Kháng sinh"],
            medicines=["Amoxicillin"],
            advice=["Nghỉ ngơi"],
            metadata={"source": "Neo4j VietMedKG"},
        )

    def test_list_diseases_no_auth_succeeds(self, client_user):
        """Knowledge list endpoint is public — no auth required."""
        client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "app.services.knowledge_service.list_diseases",
            new_callable=AsyncMock,
            return_value=self._disease_list_return(),
        ):
            resp = client.get("/api/v1/knowledge/diseases")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body

    def test_list_diseases_with_query(self, client_user):
        with patch(
            "app.services.knowledge_service.list_diseases",
            new_callable=AsyncMock,
            return_value=self._disease_list_return(),
        ) as mock_svc:
            resp = TestClient(app).get("/api/v1/knowledge/diseases?q=viêm&limit=5&offset=0")
        assert resp.status_code == 200

    def test_list_diseases_returns_correct_shape(self, client_user):
        with patch(
            "app.services.knowledge_service.list_diseases",
            new_callable=AsyncMock,
            return_value=self._disease_list_return(),
        ):
            resp = TestClient(app).get("/api/v1/knowledge/diseases")
        item = resp.json()["items"][0]
        assert "id" in item
        assert "disease_name" in item

    def test_get_disease_detail_200(self, client_user):
        with patch(
            "app.services.knowledge_service.get_disease",
            new_callable=AsyncMock,
            return_value=self._disease_detail_return(),
        ):
            resp = TestClient(app).get("/api/v1/knowledge/diseases/Vi%C3%AAm%20ph%E1%BB%95i")
        assert resp.status_code == 200
        body = resp.json()
        assert body["disease_name"] == "Viêm phổi"
        assert "symptoms" in body
        assert "treatments" in body
        assert "medicines" in body
        assert "advice" in body

    def test_get_disease_not_found_returns_404(self, client_user):
        from fastapi import HTTPException
        with patch(
            "app.services.knowledge_service.get_disease",
            new_callable=AsyncMock,
            side_effect=HTTPException(
                status_code=404,
                detail={"error_code": "DISEASE_NOT_FOUND", "message": "Not found"},
            ),
        ):
            resp = TestClient(app).get("/api/v1/knowledge/diseases/UNKNOWN_XYZ")
        assert resp.status_code == 404


class TestAdminEndpoints:
    def _metrics_return(self):
        from app.models.contracts import AdminMetricsResponse
        return AdminMetricsResponse(
            request_count=100,
            average_latency_ms=600.0,
            p95_latency_ms=2000.0,
            negative_feedback_rate=0.05,
            engine_usage={"lightrag": 70, "cypher_direct": 30},
            pending_review_count=3,
        )

    def _review_queue_return(self):
        from app.models.contracts import ReviewItemRecord, ReviewQueueResponse
        return ReviewQueueResponse(
            items=[
                ReviewItemRecord(
                    id=str(uuid4()),
                    status="pending",
                    category="answer_quality",
                    feedback_id=str(uuid4()),
                    message_id=str(uuid4()),
                    conversation_id=str(uuid4()),
                    rating="down",
                    reason="incorrect",
                    comment=None,
                    created_at="2026-06-11T00:00:00+00:00",
                )
            ],
            total=1,
            limit=20,
            offset=0,
        )

    def test_metrics_requires_admin(self, client_user):
        """Non-admin user must get 403."""
        resp = client_user.get(
            "/api/v1/admin/metrics",
            headers=_user_headers(),
        )
        assert resp.status_code == 403

    def test_metrics_no_auth_returns_401(self, client_admin):
        resp = TestClient(app, raise_server_exceptions=False).get("/api/v1/admin/metrics")
        assert resp.status_code == 401

    def test_metrics_admin_200(self, client_admin):
        with patch(
            "app.services.analytics_service.get_admin_metrics",
            new_callable=AsyncMock,
            return_value=self._metrics_return(),
        ):
            resp = client_admin.get("/api/v1/admin/metrics", headers=_admin_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert "request_count" in body
        assert "average_latency_ms" in body
        assert "p95_latency_ms" in body
        assert "negative_feedback_rate" in body
        assert "engine_usage" in body
        assert "pending_review_count" in body

    def test_review_queue_requires_admin(self, client_user):
        resp = client_user.get(
            "/api/v1/admin/review-items",
            headers=_user_headers(),
        )
        assert resp.status_code == 403

    def test_review_queue_admin_200(self, client_admin):
        with patch(
            "app.services.analytics_service.get_review_queue",
            new_callable=AsyncMock,
            return_value=self._review_queue_return(),
        ):
            resp = client_admin.get("/api/v1/admin/review-items", headers=_admin_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body

    def test_review_queue_item_has_required_fields(self, client_admin):
        with patch(
            "app.services.analytics_service.get_review_queue",
            new_callable=AsyncMock,
            return_value=self._review_queue_return(),
        ):
            resp = client_admin.get("/api/v1/admin/review-items", headers=_admin_headers())

        item = resp.json()["items"][0]
        required = {"id", "status", "category", "feedback_id", "message_id", "conversation_id", "rating", "created_at"}
        assert required.issubset(set(item.keys()))

    def test_review_queue_pagination_params(self, client_admin):
        with patch(
            "app.services.analytics_service.get_review_queue",
            new_callable=AsyncMock,
            return_value=self._review_queue_return(),
        ) as mock_svc:
            resp = client_admin.get(
                "/api/v1/admin/review-items?limit=5&offset=10",
                headers=_admin_headers(),
            )
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(limit=5, offset=10)
