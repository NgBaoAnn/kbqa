# Clean Architecture Blueprint — AegisHealth KBQA

> **Pattern:** Modular Monolith + Clean Architecture (Hexagonal / Ports & Adapters)
> **Status:** ✅ Implemented (Phase 0–5 complete, 2026-06-16)
> **Entry point:** `uvicorn api.app:app --app-dir src`

---

## 1. Lý do chọn Modular Monolith

| Tiêu chí | Microservices | **Modular Monolith ✅** |
|----------|---------------|------------------------|
| Team size (1–3 người) | Overhead quá lớn | Phù hợp |
| Deployment | Cần K8s/Docker Compose | Single process, đơn giản |
| AI Engine latency | Network hop thêm 5–50 ms | In-process, ~0 ms |
| Shared Neo4j connection | Cần connection pooling riêng | Shared driver singleton |
| Data consistency | Eventual consistency phức tạp | Single transaction |
| Testing | Integration tests cần Docker | In-memory adapters đủ |
| Future migration | — | Dễ tách Microservice khi cần |

---

## 2. Dependency Rule (Bất biến)

```
Adapters ──► Ports ──► Domain
  (Infrastructure)    (Entities + Interfaces)
                ▲
         Use Cases (Application)
                ▲
         API Routers (HTTP Layer)
```

- **Domain** KHÔNG import từ bất kỳ layer nào khác.
- **Use Cases** CHỈ import Domain entities + Ports.
- **Adapters** implement Ports, KHÔNG import Use Cases.
- **Routers** CHỈ gọi Use Cases, KHÔNG gọi trực tiếp Domain/Adapters.

---

## 3. Cấu trúc thư mục (TO-BE)

```
kbqa/
├── src/                              # ── Toàn bộ Python source code ──
│   │
│   ├── domain/                       # 🟢 INNERMOST — Pure business logic
│   │   ├── qa/
│   │   │   ├── pipeline.py           # Pipeline orchestration (no I/O)
│   │   │   ├── intent_classifier.py  # Regex + LLM intent extraction
│   │   │   ├── cypher_builder.py     # Text-to-Cypher templates
│   │   │   ├── answer_synthesizer.py # LLM answer synthesis
│   │   │   ├── safety_policy.py      # Safety classification (SafetyVO)
│   │   │   ├── source_policy.py      # Source normalization (SourceRecord)
│   │   │   └── value_objects.py      # QueryType, EntityName, etc.
│   │   ├── conversation/             # Message, Conversation entities
│   │   ├── knowledge/                # Disease, Symptom entities
│   │   ├── user/                     # UserProfile, UserPreferences
│   │   └── shared/
│   │       ├── errors.py             # Domain exceptions
│   │       └── types.py              # Shared type aliases
│   │
│   ├── ports/                        # 🟢 ABSTRACT INTERFACES
│   │   ├── llm.py                    # ILlmProvider
│   │   ├── graph.py                  # IGraphRepository
│   │   ├── vector.py                 # IVectorRepository
│   │   ├── database.py               # IDatabaseRepository
│   │   └── auth.py                   # IAuthProvider
│   │
│   ├── use_cases/                    # 🔵 APPLICATION LAYER
│   │   ├── answer_question.py        # Main QA use case (→ AIServiceResult)
│   │   ├── answer_question_stream.py # Streaming variant (SSE)
│   │   ├── manage_conversation.py    # CRUD conversations + message persistence
│   │   ├── manage_feedback.py        # Feedback submission
│   │   ├── explore_knowledge.py      # KG browsing (list/get diseases)
│   │   ├── manage_preferences.py     # User preferences CRUD
│   │   └── admin_analytics.py        # Admin metrics + review queue
│   │
│   ├── adapters/                     # 🔴 OUTERMOST — Infrastructure
│   │   ├── neo4j/
│   │   │   ├── driver.py             # Singleton driver management
│   │   │   └── graph_repository.py   # IGraphRepository → Neo4j AuraDB
│   │   ├── lightrag/
│   │   │   ├── vector_repository.py  # IVectorRepository → LightRAG + Qdrant
│   │   │   ├── llm_adapter.py        # Ollama/vLLM wrapper for LightRAG
│   │   │   └── embedding_adapter.py  # bge-m3 embedding wrapper
│   │   ├── supabase/
│   │   │   ├── database_repository.py # IDatabaseRepository → Supabase Postgres
│   │   │   └── auth_provider.py       # IAuthProvider → Supabase JWT
│   │   ├── ollama/
│   │   │   └── llm_provider.py        # ILlmProvider → OpenAI-compat endpoint
│   │   └── in_memory/                 # Test doubles (no external deps)
│   │       ├── graph_repository.py    # Basic Cypher string matching
│   │       ├── vector_repository.py   # Dict-based vector mock
│   │       ├── database.py            # Stateful in-memory store
│   │       └── llm_provider.py        # Preset response provider
│   │
│   ├── api/                          # 🟠 API GATEWAY — FastAPI HTTP layer
│   │   ├── app.py                    # FastAPI app factory (create_app)
│   │   ├── config.py                 # ✅ SINGLE config (all env vars → Settings)
│   │   ├── dependencies.py           # AppContainer — DI wiring
│   │   ├── middleware/
│   │   │   ├── cors.py               # add_cors_middleware()
│   │   │   ├── rate_limit.py         # RateLimitMiddleware (sliding window)
│   │   │   └── auth.py               # get_current_user, require_role
│   │   ├── routers/                  # Thin HTTP handlers (parse→use case→format)
│   │   │   ├── health.py             # GET /health
│   │   │   ├── query.py              # POST /api/v1/query
│   │   │   ├── conversations.py      # /api/v1/conversations + SSE stream
│   │   │   ├── feedback.py           # POST /api/v1/messages/{id}/feedback
│   │   │   ├── knowledge.py          # GET /api/v1/knowledge/diseases
│   │   │   ├── me.py                 # GET/PATCH /api/v1/me/preferences
│   │   │   └── admin.py              # GET /api/v1/admin/metrics
│   │   └── schemas/                  # Pydantic models (split from contracts.py)
│   │       ├── requests.py           # Inbound request schemas
│   │       ├── responses.py          # Outbound response schemas
│   │       └── streaming.py          # SSE event schemas + builder helpers
│   │
│   └── prompts/                      # Prompt templates (shared resource)
│       ├── text_to_cypher.md
│       ├── intent_system.md
│       └── medical_user.md
│
├── tests/
│   ├── unit/
│   │   ├── domain/                   # Pure domain logic tests (no I/O)
│   │   ├── use_cases/                # Use case tests with in-memory adapters
│   │   └── adapters/                 # Adapter unit tests
│   └── integration/                  # Requires live Neo4j / Supabase
│
├── data_pipeline/                    # ETL & Data Tooling (standalone CLI)
├── frontend/                         # React 19 + Vite + TypeScript (unchanged)
└── pyproject.toml                    # src layout: packages = [{include = "src"}]
```

---

## 4. Port Interfaces

```python
# src/ports/graph.py
class IGraphRepository(ABC):
    async def execute_cypher(self, query: str, params: dict | None = None) -> list[dict]: ...
    async def find_diseases_by_name(self, name: str, limit: int = 30) -> list[str]: ...
    async def get_schema_info(self) -> dict: ...
    async def check_connectivity(self) -> bool: ...

# src/ports/vector.py
class IVectorRepository(ABC):
    async def query(self, question: str, mode: str = "naive") -> dict: ...
    async def query_stream(self, question: str, mode: str = "naive") -> tuple[str, AsyncIterator[str]]: ...
    async def health_check(self) -> dict: ...

# src/ports/database.py
class IDatabaseRepository(ABC):
    def fetch_one(self, query: str, params: tuple = ()) -> dict | None: ...
    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]: ...
    def execute(self, query: str, params: tuple = ()) -> None: ...
    def transaction(self) -> ContextManager: ...

# src/ports/llm.py
class ILlmProvider(ABC):
    async def chat_completion(self, messages: list[dict], *, temperature: float = 0.0) -> str: ...
    async def chat_completion_stream(self, messages: list[dict]) -> AsyncIterator[str]: ...
    async def check_availability(self) -> bool: ...
```

---

## 5. Dependency Injection — AppContainer

`src/api/dependencies.py` là **composition root** duy nhất.

```python
@dataclass
class AppContainer:
    graph: IGraphRepository          # Neo4jGraphRepository
    vector: IVectorRepository        # LightragVectorRepository
    db: IDatabaseRepository          # SupabaseDatabaseRepository
    auth: IAuthProvider              # SupabaseAuthProvider
    llm: ILlmProvider                # OllamaLlmProvider
    embedding: IEmbeddingProvider    # OllamaEmbeddingProvider
    answer_question: AnswerQuestionUseCase
    answer_question_stream: AnswerQuestionStreamUseCase

    @classmethod
    async def create(cls, settings: Settings) -> "AppContainer": ...
```

`AppContainer` được khởi tạo trong **FastAPI lifespan** và lưu vào `app.state.container`.  
Routers truy cập qua `request.app.state.container`.

---

## 6. Query Pipeline — Luồng xử lý chính

```
User → POST /api/v1/conversations/{id}/messages
         │
         ▼
  [Router] parse request, get CurrentUser
         │
         ▼
  ManageConversationUseCase.persist_user_message()
         │
         ▼
  AnswerQuestionUseCase.execute(question, mode, preferences)
         │
         ├─► QAPipeline.run(question)
         │       │
         │       ├─► IntentClassifier.classify()    ← LLM extraction / regex fallback
         │       │
         │       ├─► [Cypher Path] entity found in KG
         │       │       ├─► graph.find_diseases_by_name()  ← disambiguate
         │       │       ├─► CypherBuilder.build()           ← template selection
         │       │       ├─► graph.execute_cypher()          ← Neo4j query
         │       │       └─► llm.chat_completion()           ← synthesize answer
         │       │
         │       └─► [LightRAG Path] no entity / fallback
         │               └─► vector.query(question, mode)   ← Qdrant semantic search
         │
         ├─► safety_policy.safety_from_response_type()
         ├─► source_policy.normalize_sources_from_pipeline()
         └─► AIServiceResult(answer, sources, safety, suggested_questions, metadata)
         │
         ▼
  ManageConversationUseCase.persist_assistant_response()
     (saves message + sources + query_log atomically)
         │
         ▼
  [Router] format ChatResponse → HTTP 201
```

---

## 7. API Endpoints

| Method | Path | Use Case | Auth |
|--------|------|----------|------|
| `GET` | `/health` | — | No |
| `GET` | `/api/v1/me` | — | Bearer |
| `GET/PATCH` | `/api/v1/me/preferences` | `ManagePreferencesUseCase` | Bearer |
| `POST` | `/api/v1/conversations` | `ManageConversationUseCase` | Bearer |
| `GET` | `/api/v1/conversations` | `ManageConversationUseCase` | Bearer |
| `GET` | `/api/v1/conversations/{id}` | `ManageConversationUseCase` | Bearer |
| `POST` | `/api/v1/conversations/{id}/messages` | `AnswerQuestionUseCase` | Bearer |
| `POST` | `/api/v1/conversations/{id}/messages/stream` | `AnswerQuestionStreamUseCase` | Bearer |
| `GET` | `/api/v1/conversations/{id}/export` | `ManageConversationUseCase` | Bearer |
| `POST` | `/api/v1/messages/{id}/feedback` | `ManageFeedbackUseCase` | Bearer |
| `GET` | `/api/v1/knowledge/diseases` | `ExploreKnowledgeUseCase` | No |
| `GET` | `/api/v1/knowledge/diseases/{id}` | `ExploreKnowledgeUseCase` | No |
| `POST` | `/api/v1/query` | `AnswerQuestionUseCase` | Bearer |
| `GET` | `/api/v1/admin/metrics` | `AdminAnalyticsUseCase` | Admin |
| `GET` | `/api/v1/admin/review-items` | `AdminAnalyticsUseCase` | Admin |

---

## 8. Schemas — Split từ `contracts.py`

| File | Nội dung |
|------|----------|
| `api/schemas/requests.py` | `ConversationCreateRequest`, `MessageCreateRequest`, `QueryRequest`, `FeedbackCreateRequest`, `UserPreferencesUpdateRequest` |
| `api/schemas/responses.py` | `ChatResponse`, `ConversationSummary`, `DiseaseListResponse`, `AdminMetricsResponse`, `SafetyPayload`, `ChatSource`, v.v. |
| `api/schemas/streaming.py` | SSE event schemas + builder helpers: `build_stage_event()`, `build_delta_event()`, `build_final_event()`, v.v. |

---

## 9. SSE Streaming Event Flow

```
event: stage    {"stage": "routing",    "message": "Đang phân tích..."}
event: stage    {"stage": "generating", "message": "Đang tạo câu trả lời..."}
event: delta    {"content": "Bệnh", "streaming_supported": true}
event: delta    {"content": " tiểu", ...}
...
event: sources  {"sources": [...]}
event: stage    {"stage": "persisting", "message": "Đang lưu..."}
event: final    {"conversation_id": "...", "message_id": "...", "answer": "..."}
```

---

## 10. In-Memory Test Doubles

Tất cả ports đều có **In-Memory Adapter** để test mà không cần infrastructure thật:

| Port | In-Memory Adapter | Capabilities |
|------|-------------------|--------------|
| `IGraphRepository` | `InMemoryGraphRepository` | `seed_disease()`, basic Cypher string matching |
| `IVectorRepository` | `InMemoryVectorRepository` | `seed_answer()`, preset `query_stream()` |
| `IDatabaseRepository` | `InMemoryDatabaseRepository` | Dict-based CRUD cho conversations, preferences, feedback |
| `ILlmProvider` | `InMemoryLlmProvider` | `set_response()`, preset `chat_completion()` |

---

## 11. Configuration — Settings

Tất cả env vars được tập trung tại `src/api/config.py` (`Settings` class, dùng `pydantic-settings`).  
Xem [04_SETUP.md](./04_SETUP.md) để biết danh sách đầy đủ các biến môi trường.

---

## 12. Khởi chạy

```bash
# Development (new src layout)
uvicorn api.app:app --app-dir src --reload --port 8000

# Legacy entry point (vẫn hoạt động)
uvicorn backend.app.main:app --reload --port 8000

# Tests
cd kbqa
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/ -q
```

---

## 13. Quyết định kiến trúc

Xem thư mục [`docs/adr/`](./adr/) để biết các Architecture Decision Records:

- [ADR-001](./adr/ADR-001-modular-monolith.md) — Adopt Modular Monolith + Clean Architecture
