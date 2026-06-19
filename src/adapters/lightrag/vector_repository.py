"""LightRAG Vector Repository Adapter — implements IVectorRepository.

Wraps the LightRAG singleton (Qdrant-backed naive vector search)
to provide semantic retrieval via the IVectorRepository port.

Extracted and refactored from ai_engine/services/lightrag_service.py.

Key responsibilities:
- Manage LightRAG singleton lifecycle (lazy init + double-checked lock).
- Override LightRAG's default prompts with Vietnamese medical prompts.
- Enforce naive mode (pure Qdrant vector search — internal LightRAG
  graph is empty; VietMedKG is served by Neo4j Cypher path).
- Provide query(), query_stream(), and health_check().
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ports.vector import IVectorRepository

logger = logging.getLogger(__name__)

# ── httpx 0.28.x workaround ──────────────────────────────────────────────
# macOS/Linux may set NO_PROXY="::1,..." which httpx 0.28 parses as
# "Invalid port: ':1'", breaking all Qdrant Cloud connections.
os.environ["NO_PROXY"] = ""
os.environ["no_proxy"] = ""

# ── Vietnamese medical prompt (overrides LightRAG English defaults) ───────
_VI_PROMPT_BASE = """\
Bạn là trợ lý y tế AegisHealth. Nhiệm vụ của bạn là trả lời câu hỏi của người dùng một cách chính xác bằng tiếng Việt, CHỈ dựa trên thông tin được cung cấp trong phần **Context**.

---Hướng dẫn---
1. Luôn luôn trả lời bằng ngôn ngữ Tiếng Việt (Vietnamese).
2. Nếu thông tin trong Context không có đáp án, hãy trả lời đúng một câu: "Xin lỗi, dữ liệu hiện tại không đủ thông tin để trả lời câu hỏi này." Không giải thích thêm.
3. Sử dụng gạch đầu dòng (-) và in đậm (**) những ý chính. Câu trả lời phải ngắn gọn.
4. Chỉ liệt kê các thông tin có sẵn trong Context. TUYỆT ĐỐI KHÔNG tự ý giải thích lý do, KHÔNG phân tích thành phần dinh dưỡng hay thêm thắt kiến thức y khoa bên ngoài.
5. Không tạo mục "References" hay chèn các thẻ [1], [2] vào cuối câu trả lời.

---Lưu ý bổ sung---
{user_prompt}

---Context---
"""

_MEDICAL_USER_PROMPT = "Luôn trả lời bằng tiếng Việt. Không đề xuất liều lượng thuốc."


def _patch_lightrag_prompts() -> None:
    """Override LightRAG's default English prompts with Vietnamese medical prompts."""
    try:
        import lightrag.prompt as p  # type: ignore[import]
        p.PROMPTS["rag_response"] = _VI_PROMPT_BASE + "{context_data}\n"
        p.PROMPTS["naive_rag_response"] = _VI_PROMPT_BASE + "{content_data}\n"
        logger.debug("LightRAG prompts patched to Vietnamese medical prompts.")
    except ImportError:
        logger.debug("lightrag not installed — skipping prompt patch")


class LightragVectorRepository(IVectorRepository):
    """Production adapter for IVectorRepository backed by LightRAG + Qdrant.

    Args:
        working_dir: LightRAG working directory for KV caches.
        llm_base_url: OpenAI-compatible LLM server base URL.
        llm_model_name: LLM model name (e.g. 'qwen2.5:14b').
        embedding_base_url: OpenAI-compatible embedding server base URL.
        embedding_model: Embedding model name (e.g. 'BAAI/bge-m3').
        embedding_dim: Embedding vector dimension (e.g. 1024).
        kg_storage: LightRAG KG storage backend (e.g. 'Neo4JStorage').
        vector_storage: LightRAG vector storage backend (e.g. 'NanoVectorDBStorage').
        doc_storage: LightRAG document storage backend (e.g. 'JsonKVStorage').
        neo4j_uri: Neo4j URI (needed when kg_storage='Neo4JStorage').
        neo4j_username: Neo4j username.
        neo4j_password: Neo4j password.
        force_naive_mode: If True, always use naive mode regardless of caller.
        default_query_mode: Default query mode when force_naive_mode=False.
        llm_timeout_seconds: HTTP timeout for LLM/embedding calls.
    """

    def __init__(
        self,
        *,
        working_dir: str = "./lightrag_data",
        llm_base_url: str = "http://localhost:11434/v1",
        llm_model_name: str = "qwen2.5:14b",
        embedding_base_url: str = "http://localhost:11434/v1",
        embedding_model: str = "BAAI/bge-m3",
        embedding_dim: int = 1024,
        kg_storage: str = "Neo4JStorage",
        vector_storage: str = "NanoVectorDBStorage",
        doc_storage: str = "JsonKVStorage",
        neo4j_uri: str = "",
        neo4j_username: str = "neo4j",
        neo4j_password: str = "",
        force_naive_mode: bool = True,
        default_query_mode: str = "naive",
        llm_timeout_seconds: int = 60,
    ) -> None:
        self._working_dir = Path(working_dir)
        self._llm_base_url = llm_base_url
        self._llm_model_name = llm_model_name
        self._embedding_base_url = embedding_base_url
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim
        self._kg_storage = kg_storage
        self._vector_storage = vector_storage
        self._doc_storage = doc_storage
        self._neo4j_uri = neo4j_uri
        self._neo4j_username = neo4j_username
        self._neo4j_password = neo4j_password
        self._force_naive_mode = force_naive_mode
        self._default_query_mode = default_query_mode
        self._llm_timeout = llm_timeout_seconds

        self._instance = None
        self._init_lock = asyncio.Lock()
        self._llm_client = None
        self._embedding_client = None

        # Patch Vietnamese prompts at construction time
        _patch_lightrag_prompts()
        logger.info(
            "LightRAG adapter configured: working_dir=%s kg_storage=%s "
            "vector_storage=%s doc_storage=%s llm_model=%s embedding_model=%s "
            "embedding_dim=%d force_naive=%s default_mode=%s timeout=%ss",
            self._working_dir,
            self._kg_storage,
            self._vector_storage,
            self._doc_storage,
            self._llm_model_name,
            self._embedding_model,
            self._embedding_dim,
            self._force_naive_mode,
            self._default_query_mode,
            self._llm_timeout,
        )

    @property
    def effective_mode(self) -> str:
        return "naive" if self._force_naive_mode else self._default_query_mode

    # ── LightRAG singleton lifecycle ──────────────────────────────────────

    async def _get_instance(self):
        """Get or lazily create the LightRAG singleton (double-checked lock)."""
        if self._instance is not None:
            return self._instance

        async with self._init_lock:
            if self._instance is not None:
                return self._instance
            self._instance = await self._create_instance()
            return self._instance

    async def warmup(self) -> None:
        """Initialize LightRAG storages before the first user query."""
        await self._get_instance()

    def _get_llm_client(self):
        """Return the shared LLM client, creating it on first use."""
        if self._llm_client is None:
            from openai import AsyncOpenAI  # type: ignore[import]
            logger.info(
                "Creating LightRAG LLM client: base_url=%s model=%s timeout=%ss",
                self._llm_base_url,
                self._llm_model_name,
                self._llm_timeout,
            )
            self._llm_client = AsyncOpenAI(
                base_url=self._llm_base_url,
                api_key="ollama",
                timeout=self._llm_timeout,
            )
        return self._llm_client

    def _get_embedding_client(self):
        """Return the shared embedding client, creating it on first use."""
        if self._embedding_client is None:
            from openai import AsyncOpenAI  # type: ignore[import]
            logger.info(
                "Creating LightRAG embedding client: base_url=%s model=%s dim=%d timeout=%ss",
                self._embedding_base_url,
                self._embedding_model,
                self._embedding_dim,
                self._llm_timeout,
            )
            self._embedding_client = AsyncOpenAI(
                base_url=self._embedding_base_url,
                api_key="ollama",
                timeout=self._llm_timeout,
            )
        return self._embedding_client

    async def _llm_func(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
        keyword_extraction: bool = False,
        **kwargs: Any,
    ) -> str | AsyncIterator[str]:
        """LightRAG-compatible LLM function."""
        client = self._get_llm_client()
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history_messages:
            messages.extend(history_messages)

        # Inject Vietnamese constraint at end of user prompt (prevents language drift)
        safe_prompt = prompt.strip()
        if not keyword_extraction:
            safe_prompt += "\n\n(Yêu cầu bắt buộc: TRẢ LỜI BẰNG TIẾNG VIỆT)"
        messages.append({"role": "user", "content": safe_prompt})

        default_tokens = 256 if keyword_extraction else 512
        max_tokens = int(kwargs.get("max_new_tokens", default_tokens))
        stream = bool(kwargs.get("stream")) and not keyword_extraction

        try:
            started = time.monotonic()
            logger.info(
                "LightRAG LLM call start: model=%s keyword_extraction=%s stream=%s "
                "max_tokens=%d prompt_chars=%d system_chars=%d history_messages=%d",
                self._llm_model_name,
                keyword_extraction,
                stream,
                max_tokens,
                len(safe_prompt),
                len(system_prompt or ""),
                len(history_messages or []),
            )
            if stream:
                response = await client.chat.completions.create(
                    model=self._llm_model_name,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=max_tokens,
                    stream=True,
                )

                async def _stream_chunks() -> AsyncIterator[str]:
                    async for chunk in response:
                        if not getattr(chunk, "choices", None):
                            continue
                        delta = getattr(chunk.choices[0], "delta", None)
                        content = getattr(delta, "content", None) if delta else None
                        if content:
                            yield content

                return _stream_chunks()

            response = await client.chat.completions.create(
                model=self._llm_model_name,
                messages=messages,
                temperature=0.1 if keyword_extraction else 0.3,
                max_tokens=max_tokens,
            )
            result = response.choices[0].message.content or ""
            logger.info(
                "LightRAG LLM call done: model=%s keyword_extraction=%s "
                "elapsed_ms=%.0f response_chars=%d total_tokens=%s",
                self._llm_model_name,
                keyword_extraction,
                (time.monotonic() - started) * 1000,
                len(result),
                response.usage.total_tokens if response.usage else "unknown",
            )
            return result
        except Exception as exc:
            logger.error(
                "LightRAG LLM call failed: model=%s keyword_extraction=%s "
                "stream=%s max_tokens=%d error=%s",
                self._llm_model_name,
                keyword_extraction,
                stream,
                max_tokens,
                exc,
            )
            raise

    async def _embedding_func(self, texts: list[str]):
        """LightRAG-compatible embedding function."""
        import numpy as np
        client = self._get_embedding_client()
        try:
            started = time.monotonic()
            logger.info(
                "LightRAG embedding call start: model=%s texts=%d",
                self._embedding_model,
                len(texts),
            )
            response = await client.embeddings.create(
                model=self._embedding_model,
                input=texts,
            )
            embeddings = [item.embedding for item in response.data]
            result = np.array(embeddings, dtype=np.float32)
            if result.shape[1] != self._embedding_dim:
                logger.warning(
                    "Embedding dimension mismatch: expected %d, got %d. "
                    "Update EMBEDDING_DIM in your .env file.",
                    self._embedding_dim,
                    result.shape[1],
                )
            logger.info(
                "LightRAG embedding call done: model=%s texts=%d shape=%s elapsed_ms=%.0f",
                self._embedding_model,
                len(texts),
                result.shape,
                (time.monotonic() - started) * 1000,
            )
            return result
        except Exception as exc:
            logger.error(
                "LightRAG embedding call failed: model=%s texts=%d error=%s",
                self._embedding_model,
                len(texts),
                exc,
            )
            raise

    async def _create_instance(self):
        """Create and configure a LightRAG instance."""
        try:
            from lightrag import LightRAG  # type: ignore[import]
            from lightrag.utils import EmbeddingFunc  # type: ignore[import]
        except ImportError as exc:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(
                "LightRAG is not installed. Run: pip install 'lightrag-hku[api]'"
            ) from exc

        self._working_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Initializing LightRAG...")
        logger.info("  Working directory: %s", self._working_dir)
        logger.info("  KG Storage: %s", self._kg_storage)
        logger.info("  Vector Storage: %s", self._vector_storage)
        logger.info("  Doc Storage: %s", self._doc_storage)
        logger.info("  LLM Model: %s", self._llm_model_name)
        logger.info("  Embedding Model: %s", self._embedding_model)
        logger.info("  Query Mode (enforced): %s", self.effective_mode)
        logger.info("  LLM/embedding timeout: %ss", self._llm_timeout)

        # Clear stale English keyword cache from previous runs
        self._clear_stale_llm_cache()

        emb_func = EmbeddingFunc(
            embedding_dim=self._embedding_dim,
            max_token_size=8192,
            func=self._embedding_func,
        )

        # Set Neo4j env vars when using Neo4JStorage
        if self._kg_storage == "Neo4JStorage" and self._neo4j_uri:
            os.environ.setdefault("NEO4J_URI", self._neo4j_uri)
            os.environ.setdefault("NEO4J_USERNAME", self._neo4j_username)
            os.environ.setdefault("NEO4J_PASSWORD", self._neo4j_password)
            logger.info("  Neo4j URI: %s", self._neo4j_uri)

        rag = LightRAG(
            working_dir=str(self._working_dir),
            llm_model_func=self._llm_func,
            embedding_func=emb_func,
            graph_storage=self._kg_storage,
            vector_storage=self._vector_storage,
            kv_storage=self._doc_storage,
            addon_params={"language": "Vietnamese"},
        )
        logger.info("Initializing LightRAG storages (mode=%s)...", self.effective_mode)
        started = time.monotonic()
        await rag.initialize_storages()
        logger.info(
            "LightRAG initialized successfully in %.0fms.",
            (time.monotonic() - started) * 1000,
        )
        return rag

    def _clear_stale_llm_cache(self) -> None:
        """Delete the LLM keyword cache if it contains English-only keywords."""
        cache_file = self._working_dir / "kv_store_llm_response_cache.json"
        if not cache_file.exists():
            logger.info("LLM cache file not found, skipping stale-cache cleanup: %s", cache_file)
            return
        try:
            import json
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Inspecting LLM cache for stale keyword entries: %s (%d records)", cache_file, len(data))
            stale = False
            for key, val in data.items():
                if "keywords" in key and isinstance(val, dict):
                    content = val.get("return", "")
                    try:
                        kw = json.loads(content) if isinstance(content, str) else content
                        if kw.get("high_level_keywords") and not kw.get("low_level_keywords"):
                            stale = True
                            break
                    except Exception:
                        pass
            if stale:
                cache_file.unlink()
                logger.info("Cleared stale LLM keyword cache: %s", cache_file)
            else:
                logger.info("LLM cache appears valid, keeping: %s", cache_file)
        except Exception as exc:
            logger.warning("Could not inspect LLM cache: %s", exc)

    # ── IVectorRepository implementation ──────────────────────────────────

    async def query(
        self,
        question: str,
        *,
        mode: str = "naive",
        only_need_context: bool = False,
    ) -> dict[str, Any]:
        """Query the LightRAG/Qdrant vector store."""
        effective_mode = self.effective_mode if self._force_naive_mode else (mode or self._default_query_mode)
        started = time.monotonic()
        logger.info(
            "Querying LightRAG (mode=%s, requested_mode=%s, only_need_context=%s): %s",
            effective_mode,
            mode,
            only_need_context,
            question[:120],
        )

        try:
            from lightrag import QueryParam  # type: ignore[import]
        except ImportError:
            return {
                "answer": "",
                "mode": effective_mode,
                "success": False,
                "error": "LightRAG is not installed.",
            }

        try:
            rag = await self._get_instance()
            logger.info(
                "LightRAG QueryParam: mode=%s only_need_context=%s top_k=20 chunk_top_k=10 "
                "max_entity_tokens=2000 max_relation_tokens=2000 max_total_tokens=6000",
                effective_mode,
                only_need_context,
            )
            param = QueryParam(
                mode=effective_mode,
                only_need_context=only_need_context,
                user_prompt=_MEDICAL_USER_PROMPT,
                top_k=20,
                chunk_top_k=10,
                max_entity_tokens=2000,
                max_relation_tokens=2000,
                max_total_tokens=6000,
            )
            result = await rag.aquery(question, param=param)
            answer = "" if result is None else str(result).strip()
            if not answer or answer.lower() == "none":
                logger.error(
                    "LightRAG returned empty answer (mode=%s, result_type=%s, elapsed_ms=%.0f)",
                    effective_mode,
                    type(result).__name__,
                    (time.monotonic() - started) * 1000,
                )
                return {
                    "answer": "",
                    "mode": effective_mode,
                    "success": False,
                    "error": "LightRAG returned empty answer.",
                }
            logger.info(
                "LightRAG query complete (mode=%s, result_type=%s, answer_length=%d, elapsed_ms=%.0f)",
                effective_mode,
                type(result).__name__,
                len(answer),
                (time.monotonic() - started) * 1000,
            )
            return {"answer": answer, "mode": effective_mode, "success": True}

        except Exception as exc:
            logger.error(
                "LightRAG query failed (mode=%s, elapsed_ms=%.0f): %s",
                effective_mode,
                (time.monotonic() - started) * 1000,
                exc,
            )
            return {
                "answer": "",
                "mode": effective_mode,
                "success": False,
                "error": str(exc),
            }

    async def query_stream(
        self,
        question: str,
        *,
        mode: str = "naive",
    ) -> tuple[str, AsyncIterator[str]]:
        """Stream a LightRAG query response."""
        effective_mode = self.effective_mode if self._force_naive_mode else (mode or self._default_query_mode)

        try:
            from lightrag import QueryParam  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("LightRAG is not installed.") from exc

        rag = await self._get_instance()
        param = QueryParam(
            mode=effective_mode,
            stream=True,
            user_prompt=_MEDICAL_USER_PROMPT,
            top_k=20,
            chunk_top_k=10,
            max_entity_tokens=2000,
            max_relation_tokens=2000,
            max_total_tokens=6000,
        )
        result = await rag.aquery(question, param=param)

        if result is None:
            raise RuntimeError("LightRAG returned empty answer.")

        if isinstance(result, str):
            if not result.strip() or result.strip().lower() == "none":
                raise RuntimeError("LightRAG returned empty answer.")
            async def _single() -> AsyncIterator[str]:
                yield result
            return effective_mode, _single()

        return effective_mode, result

    async def health_check(self) -> dict[str, Any]:
        """Check LightRAG + LLM + embedding health."""
        qdrant_url = os.environ.get("QDRANT_URL", "(not set)")
        health: dict[str, Any] = {
            "lightrag": "unknown",
            "query_mode": self.effective_mode,
            "force_naive": self._force_naive_mode,
            "llm_server": "unknown",
            "embedding_server": "unknown",
            "llm_model": self._llm_model_name,
            "embedding_model": self._embedding_model,
            "qdrant_url": qdrant_url[:40] + "…" if len(qdrant_url) > 40 else qdrant_url,
        }

        # LLM availability
        try:
            client = self._get_llm_client()
            resp = await client.chat.completions.create(
                model=self._llm_model_name,
                messages=[{"role": "user", "content": "Say ok."}],
                max_tokens=5,
            )
            health["llm_server"] = "available" if resp.choices else "unavailable"
        except Exception as exc:
            health["llm_server"] = f"unavailable: {exc}"

        # Embedding availability
        try:
            result = await self._embedding_func(["test"])
            health["embedding_server"] = "available" if result.shape[0] == 1 else "unavailable"
        except Exception as exc:
            health["embedding_server"] = f"unavailable: {exc}"

        # LightRAG instance
        try:
            rag = await self._get_instance()
            health["lightrag"] = "initialized" if rag else "not_initialized"
        except Exception as exc:
            health["lightrag"] = f"error: {exc}"

        return health
