# AegisHealth KBQA

A Vietnamese medical QA system combining a Knowledge Graph (Neo4j/VietMedKG) with semantic retrieval (LightRAG + Qdrant) to answer natural-language health questions accurately and with traceable sources.

> **Disclaimer:** For informational reference only — does not replace professional medical advice.

---

## Project Overview

AegisHealth KBQA routes user questions through a hybrid pipeline:

- **Cypher Path** — structured Neo4j queries for precise, deterministic lookups (~50–100 ms)
- **LightRAG Path** — semantic vector search (Qdrant) for open-ended questions
- **Auto Fallback** — if Cypher returns zero results, the system switches to LightRAG automatically

Built on a Modular Monolith + Clean Architecture (Hexagonal / Ports & Adapters) with SSE streaming, Supabase auth (roles: `user`, `reviewer`, `admin`), and a React 19 frontend.

| Layer | Technology |
|---|---|
| Backend | FastAPI · Python 3.11+ |
| Frontend | React 19 · Vite · TypeScript |
| Knowledge Graph | Neo4j AuraDB (VietMedKG, ~4,000 diseases) |
| Semantic Retrieval | LightRAG-HKU · Qdrant · bge-m3 embeddings |
| LLM | Ollama / vLLM (OpenAI-compatible) |
| Auth & Database | Supabase (JWT + Postgres) |
| Deployment | AWS EC2 · Nginx · systemd · GitHub Actions |

---

## Environment Setup

### Prerequisites

- Python >= 3.11, Node.js >= 18
- Neo4j AuraDB account (or local Neo4j)
- Supabase project (Auth + Postgres)
- Ollama or vLLM serving an OpenAI-compatible endpoint
- Qdrant Cloud or local Qdrant

### Backend

```bash
cp src/.env.example src/.env   # hoặc tạo src/.env trực tiếp
```

| Variable | Description |
|---|---|
| `NEO4J_URI` | `neo4j+ssc://xxx.databases.neo4j.io` |
| `NEO4J_USERNAME` / `NEO4J_PASSWORD` | Neo4j AuraDB credentials |
| `SUPABASE_URL` | `https://xxx.supabase.co` |
| `SUPABASE_JWT_SECRET` | JWT secret (Supabase Settings → API) |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (server-side only) |
| `SUPABASE_DB_URL` | Postgres connection string |
| `SUPABASE_ANON_KEY` | Public anon key |
| `LLM_BASE_URL` | Ollama/vLLM endpoint (default: `http://localhost:11434/v1`) |
| `LLM_MODEL_NAME` | e.g. `qwen2.5:3b` |
| `LLM_TIMEOUT_SECONDS` | LLM request timeout (default: `60`) |
| `QDRANT_URL` | Qdrant Cloud endpoint URL |
| `QDRANT_API_KEY` | Qdrant API key |
| `LIGHTRAG_WORKING_DIR` | Working directory for LightRAG data (default: `./lightrag_data`) |
| `LIGHTRAG_KG_STORAGE` | KG storage backend (default: `Neo4JStorage`) |
| `LIGHTRAG_VECTOR_STORAGE` | Vector storage backend (default: `QdrantVectorDBStorage`) |
| `DEFAULT_QUERY_MODE` | LightRAG mode: `naive` / `local` / `mix` |
| `FORCE_LIGHTRAG_NAIVE_MODE` | Set `true` if LightRAG internal graph is not built |
| `EMBEDDING_MODEL` | Embedding model name (default: `bge-m3`) |
| `EMBEDDING_DIM` | Embedding dimension (default: `1024`) |
| `EMBEDDING_BASE_URL` | Embedding server endpoint (default: `http://localhost:11434/v1`) |
| `API_HOST` / `API_PORT` | Server bind address (default: `0.0.0.0:8000`) |
| `API_CORS_ORIGINS` | Allowed CORS origins (comma-separated) |
| `RATE_LIMIT_PER_MINUTE` | Rate limit for public endpoints (default: `30`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |

### Frontend

```bash
cp frontend/.env.example frontend/.env
```

| Variable | Description |
|---|---|
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | Supabase project settings |
| `VITE_API_BASE_URL` | Backend URL (default: `http://localhost:8000`) |

---

## Dependency Installation

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend && npm install
```

---

## How to Train the Model (Data Pipeline)

The knowledge graph is built from **VietMedKG** (HySonLab, ACM TALLIP 2025).

**Step 1 — Import VietMedKG into Neo4j:**

```bash
python etl/graph_builder/build_graph.py --batch-size 500
# Dry run: --dry-run | Clear existing graph first: --clear
```

**Step 2 — Apply Supabase migrations:**

Apply SQL files from `migrations/` via Supabase Dashboard (SQL Editor) or CLI.

**Step 3 (Optional) — Sync LightRAG entities into Neo4j** (needed for `local`/`mix` modes):

```bash
python scripts/ingest_to_neo4j.py
```

**Step 4 (Optional) — Index documents into LightRAG / Qdrant:**

```bash
python scripts/index_documents.py
```

---

## How to Run Inference

### Start the backend

```bash
uvicorn api.app:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/api/v1/health

### Start the frontend

```bash
cd frontend && npm run dev   # http://localhost:5173
```

### Query the API directly

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Bệnh tiểu đường có triệu chứng gì?"}'
```

### Run evaluation

```bash
python eval/eval_golden_test.py   # 50+ question golden test set
python eval/run_benchmark.py      # Multi-model benchmark
```

---

## Deployment

The system runs as a **single process on AWS EC2** behind **Nginx** (static frontend + API reverse proxy), managed by **systemd**.

**CI/CD:** GitHub Actions (`.github/workflows/deploy-ec2.yml`) triggers on push to `dev`, SSHes into EC2, and runs `scripts/deploy_ec2.sh`.

**What the deploy script does:**

1. Pulls latest code from `origin/dev`
2. Updates Python virtualenv (`pip install -e .`)
3. Builds frontend (`npm ci && npm run build`)
4. Publishes `frontend/dist/` to `/var/www/kbqa` (Nginx web root)
5. Restarts `kbqa-backend` systemd service and reloads Nginx
6. Verifies backend and frontend are reachable

**Manual deploy:**

```bash
bash scripts/deploy_ec2.sh
```

**Required GitHub Secrets:** `AWS_EC2_HOST`, `AWS_EC2_SSH_KEY`, `AWS_EC2_USER`, `AWS_EC2_PORT`, `AWS_EC2_APP_DIR`, `AWS_EC2_DEPLOY_BRANCH`.
