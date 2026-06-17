# Kiến trúc Hệ thống

> **Xem tài liệu kiến trúc đầy đủ tại:** [08_CLEAN_ARCHITECTURE.md](./08_CLEAN_ARCHITECTURE.md)

Tài liệu này tóm tắt kiến trúc AS-IS (trước khi refactor) và TO-BE (sau Phase 0–5).

---

## AS-IS (Trước refactor)

Kiến trúc monolith đơn giản — backend và AI engine tách nhau nhưng còn nhiều coupling trực tiếp:

```
kbqa/
├── backend/          # FastAPI backend
│   └── app/
│       ├── main.py              # Entrypoint, middleware, router registration
│       ├── config.py            # Env vars: Supabase, Neo4j, API settings
│       ├── models/contracts.py  # 25+ Pydantic models trong 1 file (567 dòng)
│       ├── routers/             # 9 router files
│       └── services/            # 16 service files (pipeline, chat, AI adapter, ...)
│
├── ai_engine/        # AI/ML core — tách khỏi backend
│   ├── config.py                # ⚠️ Trùng lặp Neo4j config với backend
│   ├── services/                # Query router, Cypher builder, LightRAG, ...
│   └── prompts/                 # Prompt templates
│
├── etl/              # Data pipeline (rải rác)
└── frontend/         # React SPA (Vite + TypeScript)
```

**Vấn đề chính:**
- `pipeline.py` (596 dòng) — God Object chứa toàn bộ routing logic
- Config trùng lặp ở 2 file (`backend/config.py` và `ai_engine/config.py`)
- `contracts.py` (567 dòng) — 25+ model lẫn lộn API contracts và internal DTOs
- Cross-module direct imports: không thể test pipeline mà không mock toàn bộ ai_engine

---

## TO-BE (Sau refactor — Modular Monolith + Clean Architecture)

Xem chi tiết tại [08_CLEAN_ARCHITECTURE.md](./08_CLEAN_ARCHITECTURE.md).

### Cấu trúc mới (`src/` layout)

```
src/
├── domain/       # 🟢 Pure business logic (no I/O)
├── ports/        # 🟢 Abstract interfaces (IGraphRepository, ILlmProvider, ...)
├── use_cases/    # 🔵 Orchestration (AnswerQuestionUseCase, ManageConversationUseCase, ...)
├── adapters/     # 🔴 Infrastructure (Neo4j, Supabase, LightRAG, Ollama, InMemory)
└── api/          # 🟠 FastAPI HTTP layer (app factory, routers, schemas, middleware)
```

### Dependency Rule

```
Domain ← Use Cases ← Routers
  ↑
Ports ← Adapters
```

### External Services

| Service | Vai trò |
|---------|---------|
| **Neo4j AuraDB** | Knowledge Graph (VietMedKG schema) |
| **Supabase** | Auth (JWT), Postgres (conversations, messages, feedback, preferences, query_logs) |
| **Qdrant Cloud** | Vector DB cho LightRAG (entities, relationships, chunks) |
| **Ollama / vLLM** | LLM server (OpenAI-compatible endpoint) |

### Query Types hỗ trợ

**Forward** (entity = tên bệnh):
`symptoms`, `cause`, `check_method`, `susceptible_population`, `medicine`, `treatment`, `advice`, `prevention`, `department`, `profile`, `linked_diseases`

**Reverse** (entity = keyword):
`find_by_symptom`, `find_by_medicine`, `find_by_nutrition_avoid`, `find_by_nutrition_eat`, `find_by_prevention`, `find_by_check_method`

**Chain** (2-hop):
`chain_linked_avoid`, `chain_linked_eat`
