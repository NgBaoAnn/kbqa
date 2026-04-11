"""Pydantic request models — QueryRequest."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request body for POST /api/v1/query.

    Attributes:
        question: The natural language question from the user.
        language: Desired response language ('vi' or 'en'). Default: 'vi'.
        mode: LightRAG query mode. Default: uses server config.
              Options: naive, local, global, hybrid, mix.
    """

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Câu hỏi ngôn ngữ tự nhiên của người dùng",
        examples=["Bệnh tiểu đường có những triệu chứng gì?"],
    )
    language: str = Field(
        default="vi",
        description="Ngôn ngữ phản hồi: 'vi' hoặc 'en'",
        pattern="^(vi|en)$",
    )
    mode: str | None = Field(
        default=None,
        description="LightRAG query mode: naive, local, global, hybrid, mix",
    )
