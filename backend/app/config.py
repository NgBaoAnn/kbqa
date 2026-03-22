"""
AegisHealth KBQA — Backend Configuration

Đọc biến môi trường từ file .env bằng pydantic-settings.
Tham chiếu: docs/11_DEVELOPMENT_INFRASTRUCTURE.md (Section 3)
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Cấu hình hệ thống, tự động đọc từ biến môi trường hoặc file .env."""

    # -- Neo4j AuraDB --
    NEO4J_URI: str = "neo4j+s://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = ""

    # -- LLM Server (Ollama / vLLM) --
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_MODEL_NAME: str = "llama3:8b-instruct-q4_0"
    LLM_TIMEOUT_SECONDS: int = 30

    # -- API Configuration --
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # -- Logging --
    LOG_LEVEL: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
