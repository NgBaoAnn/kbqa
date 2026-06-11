"""Pydantic response models — QueryResponse, HealthResponse, SchemaResponse."""

from typing import Any

from pydantic import BaseModel, Field


class QueryMetadata(BaseModel):
    """Metadata included in query responses."""

    query_mode: str = Field(default="hybrid", description="LightRAG query mode used")
    execution_time_ms: float = Field(default=0, description="Total execution time (ms)")
    source_count: int = Field(default=0, description="Number of data sources/items")
    engine: str = Field(default="lightrag", description="AI engine used: 'lightrag' or 'cypher_direct'")
    cypher: str | None = Field(default=None, description="Executed Cypher query (only for cypher_direct engine)")
    error_code: str | None = Field(default=None, description="Error code if failed")
    error_detail: str | None = Field(default=None, description="Error details (dev mode)")


class QueryResponse(BaseModel):
    """Response body for POST /api/v1/query.

    Follows the Backend-Driven UI pattern: the response_type field
    tells the client which renderer component to use.
    """

    status: str = Field(description="'success' or 'error'")
    response_type: str = Field(
        description="UI rendering directive: 'table', 'text', or 'warning'"
    )
    answer: str = Field(description="Natural language answer")
    data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Structured data for table rendering (null for text/warning)",
    )
    metadata: QueryMetadata = Field(description="Query metadata and diagnostics")


class ServiceStatus(BaseModel):
    """Status of an individual service component."""

    api: str = Field(default="running", description="FastAPI backend process status")
    supabase_postgres: str = Field(default="unknown", description="Supabase Postgres connectivity")
    neo4j: str = Field(default="unknown", description="Neo4j knowledge graph connectivity")
    ai_engine: str = Field(default="unknown", description="AI engine module and config status")
    llm_server: str = Field(default="unknown", description="LLM server reachability (LightRAG)")
    embedding_server: str = Field(default="unknown", description="Embedding server reachability (LightRAG)")
    lightrag: str = Field(default="unknown", description="LightRAG instance status")


class HealthResponse(BaseModel):
    """Response body for GET /api/v1/health."""

    status: str = Field(description="Overall health status")
    services: ServiceStatus = Field(description="Individual service statuses")
    version: str = Field(description="API version")
