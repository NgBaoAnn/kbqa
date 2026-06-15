# Kiến trúc Hệ thống

## Cấu trúc Monorepo

```
kbqa/
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── main.py              # Entrypoint, middleware, router registration
│   │   ├── config.py            # Env vars: Supabase, Neo4j, API settings
│   │   ├── database.py          # Supabase Postgres access layer (psycopg)
│   │   ├── api_gateway/         # Auth dependencies (JWT verification)
│   │   ├── models/              # Pydantic contracts (request/response)
│   │   ├── routers/             # API route handlers
│   │   └── services/            # Business logic layer
│   ├── migrations/supabase/     # SQL migrations (versions, rollbacks, seeds)
│   └── tests/                   # pytest test suites
│
├── ai_engine/        # AI/ML core (tách khỏi backend)
│   ├── config.py                # LLM, Embedding, Neo4j, LightRAG settings
│   ├── services/                # Query router, Cypher builder, LightRAG, etc.
│   ├── prompts/                 # Prompt templates (text_to_cypher)
│   ├── eval/                    # Benchmark & golden test set
│   └── utils/                   # Response formatter, helpers
│
├── etl/              # Data pipeline
│   ├── data_cleaning/           # CSV preprocessing
│   └── graph_builder/           # build_graph.py — CSV → Neo4j import
│
├── frontend/         # React SPA (Vite + TypeScript)
│   └── src/
│       ├── App.tsx              # Auth-aware root component
│       ├── features/            # chat, auth, admin, settings, knowledge
│       ├── components/          # ResponseRenderer, FeedbackControls, SourcePanel
│       └── services/            # api.ts, supabase.ts
│
├── scripts/          # Utility scripts
│   ├── ingest_to_neo4j.py       # Qdrant → Neo4j sync (LightRAG entities)
│   └── deploy_ec2.sh            # EC2 deployment script
│
├── data/             # preprocessed_data.csv (~63MB)
└── pyproject.toml    # Python project config, dependencies
```

## Luồng xử lý chính (Query Pipeline)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. User gửi câu hỏi qua Frontend                              │
│  2. Frontend call POST /api/v1/conversations/{id}/messages      │
│  3. chat_service → ai_service → pipeline.run_pipeline()         │
│                                                                  │
│  4. Pipeline:                                                    │
│     a. extract_intent_with_llm()    ← LLM structured extraction │
│     b. classify_cypher_intent()     ← Regex fallback             │
│     c. Routing decision:                                         │
│        - entity in KG  → Cypher Path (Neo4j direct query)        │
│        - entity not in KG / no entity → LightRAG Path            │
│        - find_by_* types → Cypher reverse query                  │
│     d. Cypher fails → auto fallback to LightRAG                  │
│                                                                  │
│  5. Response → chat_service persists messages → return to client  │
└─────────────────────────────────────────────────────────────────┘
```

## Query Types hỗ trợ

### Forward (entity = tên bệnh)
`symptoms`, `cause`, `check_method`, `susceptible_population`, `medicine`, `treatment`, `advice`, `prevention`, `department`, `profile`, `linked_diseases`

### Reverse (entity = keyword)
`find_by_symptom`, `find_by_medicine`, `find_by_nutrition_avoid`, `find_by_nutrition_eat`, `find_by_prevention`, `find_by_check_method`

### Chain (2-hop)
`chain_linked_avoid`, `chain_linked_eat`

## External Services

| Service | Vai trò |
|---|---|
| **Neo4j AuraDB** | Knowledge Graph (VietMedKG schema + LightRAG `:base` nodes) |
| **Supabase** | Auth (JWT), Postgres (conversations, messages, feedback, preferences, query_logs) |
| **Qdrant Cloud** | Vector DB cho LightRAG (entities, relationships, chunks) |
| **Ollama / vLLM** | LLM server (OpenAI-compatible endpoint) |
