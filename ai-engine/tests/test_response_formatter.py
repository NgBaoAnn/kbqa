"""Unit tests for Response Formatter."""

import pytest

from ai_engine.utils.response_formatter import (
    classify_response_type,
    extract_table_data,
    format_error_response,
    format_lightrag_response,
    format_warning_answer,
)


class TestClassifyResponseType:
    """Test response type classification."""

    def test_warning_on_chest_pain(self):
        """Should classify as warning when chest pain is mentioned."""
        assert classify_response_type("tôi bị đau ngực", "...") == "warning"

    def test_warning_on_difficulty_breathing(self):
        """Should classify as warning for breathing difficulties."""
        assert classify_response_type("khó thở", "answer text") == "warning"

    def test_warning_on_english_emergency(self):
        """Should classify as warning for English emergency keywords."""
        assert classify_response_type("severe chest pain", "...") == "warning"

    def test_table_on_list_response(self):
        """Should classify as table when answer contains list items."""
        answer = "Triệu chứng:\n- Sốt\n- Ho\n- Khó thở"
        assert classify_response_type("triệu chứng viêm phổi", answer) == "table"

    def test_text_on_explanation(self):
        """Should classify as text for simple explanations."""
        answer = "Viêm phổi là bệnh nhiễm trùng phổi."
        assert classify_response_type("viêm phổi là gì", answer) == "text"


class TestExtractTableData:
    """Test table data extraction from text."""

    def test_extract_bullet_list(self):
        """Should extract bullet-point list items."""
        text = "Triệu chứng:\n- Sốt\n- Ho\n- Đau đầu"
        data = extract_table_data(text)
        assert data is not None
        assert len(data) == 3
        assert data[0]["item"] == "Sốt"

    def test_extract_numbered_list(self):
        """Should extract numbered list items."""
        text = "Phương pháp:\n1. Thuốc kháng sinh\n2. Nghỉ ngơi\n3. Uống nước"
        data = extract_table_data(text)
        assert data is not None
        assert len(data) == 3

    def test_no_extraction_on_plain_text(self):
        """Should return None for plain text without lists."""
        text = "Viêm phổi là bệnh nhiễm trùng phổi do vi khuẩn."
        data = extract_table_data(text)
        assert data is None


class TestFormatLightragResponse:
    """Test full response formatting."""

    def test_success_text_response(self):
        """Should format a successful text response."""
        result = format_lightrag_response(
            raw_answer="Viêm phổi là bệnh nhiễm trùng phổi.",
            question="viêm phổi là gì",
            query_mode="hybrid",
            execution_time_ms=150.5,
        )

        assert result["status"] == "success"
        assert result["response_type"] == "text"
        assert "Viêm phổi" in result["answer"]
        assert "tham khảo" in result["answer"]  # Disclaimer
        assert result["metadata"]["query_mode"] == "hybrid"
        assert result["metadata"]["engine"] == "lightrag"

    def test_empty_answer_returns_not_found(self):
        """Should return 'not found' message for empty answers."""
        result = format_lightrag_response(
            raw_answer="",
            question="test",
            query_mode="hybrid",
            execution_time_ms=100,
        )

        assert result["status"] == "success"
        assert "Không tìm thấy" in result["answer"]
        assert result["metadata"]["source_count"] == 0

    def test_warning_response_has_emergency_cta(self):
        """Warning responses should include emergency CTA."""
        result = format_lightrag_response(
            raw_answer="Đau ngực có thể liên quan đến nhồi máu cơ tim.",
            question="tôi bị đau ngực dữ dội",
            query_mode="hybrid",
            execution_time_ms=200,
        )

        assert result["response_type"] == "warning"
        assert "CẢNH BÁO" in result["answer"]
        assert "CẤP CỨU" in result["answer"]


class TestFormatErrorResponse:
    """Test error response formatting."""

    def test_error_response_structure(self):
        """Error response should have correct structure."""
        result = format_error_response(
            error_code="MODEL_UNAVAILABLE",
            error_message="Connection refused",
            user_message="Dịch vụ AI không khả dụng.",
            execution_time_ms=50.0,
        )

        assert result["status"] == "error"
        assert result["response_type"] == "text"
        assert result["data"] is None
        assert result["metadata"]["error_code"] == "MODEL_UNAVAILABLE"
        assert result["metadata"]["engine"] == "lightrag"
