# Hướng dẫn Cài đặt & Chạy

## Yêu cầu

- Python ≥ 3.11
- Node.js ≥ 18
- Neo4j AuraDB account (hoặc local Neo4j)
- Supabase project (Auth + Postgres)
- Ollama hoặc vLLM (LLM server)

## 1. Clone & cài đặt Python

```bash
git clone <repo-url>
cd kbqa

# Tạo virtualenv
python -m venv .venv
source .venv/bin/activate

# Cài đặt dependencies (editable mode)
pip install -e ".[dev]"
```

## 2. Cấu hình Environment

### Backend

```bash
cp backend/.env.example backend/.env
# Sửa backend/.env:
```

| Biến | Mô tả |
|---|---|
| `NEO4J_URI` | `neo4j+s://xxx.databases.neo4j.io` |
| `NEO4J_USERNAME` / `NEO4J_PASSWORD` | Credentials Neo4j |
| `SUPABASE_URL` | `https://xxx.supabase.co` |
| `SUPABASE_JWT_SECRET` | JWT secret (Settings → API) |
| `SUPABASE_DB_URL` | Postgres connection string |
| `LLM_BASE_URL` | Ollama endpoint (default: `http://localhost:11434/v1`) |
| `LLM_MODEL_NAME` | Model name (vd: `qwen2.5:14b`) |
| `DEFAULT_QUERY_MODE` | LightRAG mode: `naive` / `local` / `mix` |

### Frontend

```bash
cp frontend/.env.example frontend/.env
# Sửa frontend/.env:
```

| Biến | Mô tả |
|---|---|
| `VITE_SUPABASE_URL` | Giống `SUPABASE_URL` |
| `VITE_SUPABASE_ANON_KEY` | Public anon key |
| `VITE_API_BASE_URL` | Backend URL (default: `http://localhost:8000`) |

## 3. Khởi tạo Database

### Neo4j — Import Knowledge Graph

```bash
python etl/graph_builder/build_graph.py --batch-size 500
# Dry run (không import): --dry-run
# Xóa graph cũ: --clear
```

### Supabase — Chạy migrations

Apply các file SQL trong `backend/migrations/supabase/versions/` lên Supabase Dashboard (SQL Editor) hoặc qua CLI.

### LightRAG — Sync entities vào Neo4j (optional)

```bash
python scripts/ingest_to_neo4j.py
```

Script này đọc entities + relationships từ Qdrant và MERGE vào Neo4j với label `:base`.

## 4. Chạy Development

### Backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

## 5. Chạy Tests

```bash
# Từ project root
pytest                           # Tất cả tests
pytest backend/tests/            # Chỉ backend
pytest ai_engine/tests/          # Chỉ AI engine
pytest --cov                     # Với coverage
```

## 6. Lint

```bash
ruff check .
ruff format .
```
