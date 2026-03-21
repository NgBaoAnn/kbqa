# 08. KẾ HOẠCH SPRINT CHI TIẾT — AegisHealth KBQA

> **Sprint Planning: Phân công theo Sprint 0 → 1 → 2**
> Trích xuất & sắp xếp lại từ `07_TASK_ASSIGNMENTS.md`, nhóm theo Sprint thay vì Milestone.

---

## Tổng quan 3 Sprints đầu

| Sprint | Tuần | Phase | Pair α | Pair β | Milestone cover |
|---|---|---|---|---|---|
| **Sprint 0** | T1–T2 | Phase 1 | A + B (Data + AI) | C + D (AI Setup) | M1, M2 (phần đầu), M3 (phần đầu) |
| **Sprint 1** | T3–T4 | Phase 1 | A + B (Load + Validate) | C + D (Prompt Tuning) | M2 (hoàn thành), M3 (hoàn thành) |
| **Sprint 2** | T5–T6 | Phase 2 | A + C (Backend) | B + D (Web Client) | M4 (phần 1) |

---

## 🔵 SPRINT 0 — Foundation Setup (Tuần 1–2)

> **Mục tiêu Sprint:** Thiết lập toàn bộ hạ tầng phát triển, phân tích dữ liệu, viết ETL scripts, setup AI model, bắt đầu viết prompt.
> **Pair α:** A (Data Lead) + B (AI Lead) → ETL + Graph Schema
> **Pair β:** C (Web Lead) + D (Mobile Lead) → Ollama Setup + Prompt v1

### Đội 1 — Data & Graph

| Task ID | Tên Công việc | Assignee | DoD | Deps | Ngày target |
|---|---|---|---|---|---|
| M1-DAT-01 | Khởi tạo monorepo GitHub (folder structure, `.gitignore`, branches) | [Data Lead] | Repo có `docs/`, `data/`, `ai-engine/`, `backend/`, `web-client/`, `mobile-client/`; branch `main` + `develop` | — | Ngày 1 |
| M1-DAT-02 | Tạo tài khoản Neo4j AuraDB Free Tier & ghi nhận URI | [Data Dev] | AuraDB instance OK, URI `neo4j+s://...` documented, `.env.example` có template | — | Ngày 1–2 |
| M1-DAT-03 | Tải datasets Kaggle (Symptom2Disease.csv, Medicine_Rec.csv) vào `data/raw/` | [Data Dev] | 2 file CSV trong `data/raw/`, báo cáo thống kê cơ bản (rows, cols, missing %) | — | Ngày 2 |
| M2-DAT-01 | Thiết kế Graph Schema: Node Labels, Properties, Constraints, Indexes | [Data Lead] | File `schema.cypher`: 3 CONSTRAINT + 3 INDEX; tài liệu schema trên Markdown | — | Ngày 3–4 |
| M2-DAT-02 | Viết EDA script phân tích Symptom2Disease.csv | [Data Dev] | `eda_symptom2disease.py` chạy OK, output: unique diseases/symptoms, missing, duplicates | M1-DAT-03 | Ngày 3–5 |
| M2-DAT-03 | Viết EDA script phân tích Medicine_Recommendation.csv | [Data Dev] | `eda_medicine.py` chạy OK, output: unique drugs, disease-drug pairs, missing | M1-DAT-03 | Ngày 3–5 |
| M2-DAT-04 | Viết ETL script: Transform Symptom2Disease → entities + relationships | [Data Dev] | `etl_pipeline.py`: lowercase, strip, dedup → output `diseases.csv`, `symptoms.csv`, `disease_symptom.csv` | M2-DAT-02 | Ngày 6–8 |
| M2-DAT-05 | Viết ETL script: Transform Medicine_Rec → entities + relationships | [Data Dev] | Output `drugs.csv` + `disease_drug.csv`, entity_id duy nhất | M2-DAT-03 | Ngày 6–8 |

### Đội 2 — AI Engine & Backend

| Task ID | Tên Công việc | Assignee | DoD | Deps | Ngày target |
|---|---|---|---|---|---|
| M1-AI-01 | Cài Ollama + pull model SLM (Llama-3-8B / Qwen-2.5-7B) | [AI Lead] | Ollama port 11434, model respond qua `curl` | — | Ngày 1–2 |
| M1-AI-02 | Khởi tạo base project FastAPI (main.py, config.py, requirements.txt) | [AI Dev] | Swagger UI chạy tại `localhost:8000/docs` | — | Ngày 1–2 |
| M1-AI-03 | Viết `.env.example` với tất cả biến môi trường | [AI Dev] | Đầy đủ: NEO4J_*, LLM_*, API_*, LOG_LEVEL | M1-DAT-02 | Ngày 3 |
| M3-AI-01 | Benchmark 2–3 model SLM trên Text-to-Cypher (10 câu mẫu) | [AI Lead] | Báo cáo: accuracy, latency, GPU RAM mỗi model; chọn model chính thức | M1-AI-01 | Ngày 3–5 |
| M3-AI-07 | Viết System Prompt v1 cho Data-to-Text & Intent Classification | [AI Lead] | `data_to_text.txt`: role, JSON output spec, ≥3 examples (table/text/warning), disclaimer | M1-AI-01 | Ngày 6–8 |
| M3-AI-09 | Viết module `cypher_validator.py` (syntax checker) | [AI Dev] | Detect syntax errors, out-of-schema labels, destructive commands; unit tests pass | — | Ngày 6–10 |

### Cả 2 Đội

| Task ID | Tên Công việc | Assignee | DoD | Deps | Ngày target |
|---|---|---|---|---|---|
| M1-ALL-01 | Review & finalize 11 tài liệu thiết kế | Cả 4 người | Tất cả docs review chéo, nộp GV phê duyệt | — | Ngày 1–5 |
| M1-ALL-02 | Setup GitHub Projects (Kanban) + Discord channels | Cả 4 người | Board 5 cột, Discord: `#daily-sync`, `#pair-alpha`, `#pair-beta` | — | Ngày 1 |

### 📊 Tổng kết Sprint 0

| Assignee | Số tasks | Trọng tâm |
|---|---|---|
| [Data Lead] | 3 | Repo setup, Graph Schema design |
| [Data Dev] | 5 | AuraDB setup, EDA, ETL scripts |
| [AI Lead] | 3 | Ollama setup, Model benchmark, Data-to-Text prompt |
| [AI Dev] | 3 | FastAPI base, `.env`, Cypher validator |
| Cả 4 | 2 | Docs review, Project tools |

### 🤝 Điểm bắt tay cuối Sprint 0
- **[Data Dev]** → **[AI Dev]**: URI AuraDB + credentials cho `.env.example`
- **Cuối Sprint**: Cả 4 demo setup cho nhau — ai cũng chạy được Neo4j + Ollama + FastAPI trên máy local

---

## 🔵 SPRINT 1 — Data Loading & Prompt Tuning (Tuần 3–4)

> **Mục tiêu Sprint:** Load dữ liệu lên AuraDB, validate graph, tạo Golden Test Set 50 câu, viết prompt Text-to-Cypher, đạt accuracy ≥ 70%.
> **Pair α:** A (Data Lead) + B (AI Lead) → Load & Validate Graph
> **Pair β:** C (Web Lead) + D (Mobile Lead) → Prompt Tuning & Eval

### Đội 1 — Data & Graph

| Task ID | Tên Công việc | Assignee | DoD | Deps | Ngày target |
|---|---|---|---|---|---|
| M2-DAT-06 | Review ETL results: data quality, cross-reference 2 datasets | [Data Lead] | 0 nulls ở `name`, 0 duplicates, disease names nhất quán giữa 2 datasets | M2-DAT-04, M2-DAT-05 | Ngày 1–2 |
| M2-DAT-07 | Viết `load_to_neo4j.py`: import nodes vào AuraDB (batch MERGE) | [Data Dev] | ≥200 Disease, ≥100 Symptom, ≥200 Drug nodes trên AuraDB; batch 1000 records | M2-DAT-01, M2-DAT-06 | Ngày 2–4 |
| M2-DAT-08 | Import relationships vào AuraDB (HAS_SYMPTOM, TREATED_BY) | [Data Dev] | Relationships OK; MATCH query đúng cho ≥10 diseases mẫu | M2-DAT-07 | Ngày 4–5 |
| M2-DAT-09 | 🤝 Validate Knowledge Graph bằng 7 loại Cypher query mẫu | [Data Lead] | Tất cả query (basic, multi-hop, stats, diff. diagnosis) pass; `validation_report.md` | M2-DAT-08 | Ngày 5–6 |
| M2-DAT-10 | 🤝 Export Schema Summary cho Đội 2 (labels, properties, stats) | [Data Lead] | `graph_schema_summary.md` đầy đủ: schema + thống kê thực tế trên AuraDB | M2-DAT-09 | Ngày 6–7 |
| M2-TEST-01 | Xây dựng Golden Test Set v1: 30 cặp (question, expected_cypher) | [Data Lead] | `golden_test_set.json`: 15 basic + 10 multi-hop + 5 statistical | M2-DAT-09 | Ngày 7–8 |
| M2-TEST-02 | Mở rộng Golden Test Set lên 50 câu (+ edge cases + tiếng Việt) | [Data Dev] | 50 cặp total: +10 tiếng Việt, +5 edge case (entity ko tồn tại, câu mập mờ) | M2-TEST-01 | Ngày 9–10 |

### Đội 2 — AI Engine & Backend

| Task ID | Tên Công việc | Assignee | DoD | Deps | Ngày target |
|---|---|---|---|---|---|
| M3-AI-02 | 🤝 Viết System Prompt v1 Text-to-Cypher (inject Schema từ Đội 1) | [AI Lead] | `text_to_cypher.txt`: role, full schema, output constraints, ≥3 few-shot | M2-DAT-10 | Ngày 7–8 ⚠️ |
| M3-AI-03 | 🤝 Bổ sung few-shot examples từ Cypher queries mẫu của Đội 1 | [AI Lead] | Prompt có ≥8 few-shot: basic, multi-hop, statistical, Vietnamese | M3-AI-02, M2-DAT-09 | Ngày 8 ⚠️ |
| M3-AI-04 | Viết script test prompt thủ công (20 câu) qua Ollama API | [AI Dev] | `test_prompt.py`: 20 câu → output (question → cypher → pass/fail) | M3-AI-02 | Ngày 8–9 |
| M3-AI-05 | 🤝 Chạy Golden Test Set → đo Cypher accuracy baseline | [AI Dev] | `eval_golden_test.py`: 50 câu, accuracy %, error taxonomy (E1–E6) | M3-AI-03, M2-TEST-01 | Ngày 9 ⚠️ |
| M3-AI-06 | Prompt tuning v1 → v1.x (target accuracy ≥ 70%) | [AI Lead] | Accuracy ≥ 70% trên Golden Test Set; changelog prompt versions | M3-AI-05 | Ngày 9–10 |
| M3-AI-08 | Test Data-to-Text prompt (15 bộ data: 5 table, 5 text, 5 warning) | [AI Dev] | JSON đúng spec; response_type chính xác ≥ 80%; disclaimer có mặt | M3-AI-07 | Ngày 3–5 |

### 📊 Tổng kết Sprint 1

| Assignee | Số tasks | Trọng tâm |
|---|---|---|
| [Data Lead] | 4 | Data quality review, Validate graph, Schema Summary, Golden Test Set v1 |
| [Data Dev] | 3 | Load nodes/rels lên AuraDB, Golden Test Set mở rộng |
| [AI Lead] | 3 | Text-to-Cypher prompt v1, Few-shot, Prompt tuning |
| [AI Dev] | 3 | Test scripts, Eval accuracy, Test Data-to-Text |

### ⚠️ Critical Path — Sprint 1
```
[Data Dev] load data (Ngày 2–5)
    → [Data Lead] validate (Ngày 5–6)
        → [Data Lead] export Schema Summary (Ngày 6–7)  ← 🤝 HANDOFF
            → [AI Lead] viết prompt v1 (Ngày 7–8)
                → [AI Dev] eval accuracy (Ngày 9)
                    → [AI Lead] prompt tuning (Ngày 9–10)
```
> **Rủi ro**: Nếu Data loading chậm → AI Team bị block. Biện pháp: AI Team dùng **schema draft** từ Sprint 0 để viết prompt skeleton trước, chỉ inject data thực sau.

### 🤝 Điểm bắt tay cuối Sprint 1
- **[Data Lead]** → **[AI Lead]**: `graph_schema_summary.md` + Cypher examples (M2-DAT-10, M2-DAT-09)
- **[Data Lead]** → **[AI Dev]**: `golden_test_set.json` 50 câu (M2-TEST-01/02)
- **Cross-review**: Cả 4 demo — Đội 1 demo Knowledge Graph, Đội 2 demo Prompt accuracy results

---

## 🟠 SPRINT 2 — Backend MVP & Web MVP (Tuần 5–6)

> **Mục tiêu Sprint:** Backend API hoạt động end-to-end, Web Client MVP hiển thị kết quả (table/text/warning).
> **⚠️ PAIR ROTATION**: Đổi pair so với Phase 1!
> **Pair α:** A (Data Lead) + C (Web Lead) → FastAPI Backend
> **Pair β:** B (AI Lead) + D (Mobile Lead) → React Web Client

### Đội 1 — Data & Graph (trong vai Backend)

| Task ID | Tên Công việc | Assignee | DoD | Deps | Ngày target |
|---|---|---|---|---|---|
| M4-BE-02 | Implement `graph_service.py`: kết nối AuraDB, execute Cypher | [Data Lead] | `execute_cypher(query) → List[Dict]`, connection pool, error handling (timeout/conn failure) | M2-DAT-09 | Ngày 1–3 |
| M4-BE-07 | 🤝 Implement `GET /api/v1/schema` (schema info endpoint) | [Data Lead] | JSON: nodes (label, count, properties), relationships (type, count, from, to) | M4-BE-02 | Ngày 4–5 |

### Đội 2 — AI Engine & Backend

| Task ID | Tên Công việc | Assignee | DoD | Deps | Ngày target |
|---|---|---|---|---|---|
| M4-BE-01 | Implement Pydantic models (`QueryRequest`, `QueryResponse`) | [AI Dev] | `models/request.py` + `response.py` match JSON spec trong `05_API_SYSTEM_DESIGN.md` | M1-AI-02 | Ngày 1–2 |
| M4-BE-03 | Implement `llm_service.py`: gọi Ollama API (OpenAI-compatible) | [AI Lead] | `/v1/chat/completions`, configurable base_url + model, timeout 30s, parse JSON | M3-AI-02, M3-AI-07 | Ngày 1–3 |
| M4-BE-04 | Implement `pipeline.py` (Orchestrator): Generate → Retrieve → Synthesize | [AI Lead] | Gọi lần lượt: LLM → validator → graph_service → LLM; retry 2x; fallback | M4-BE-02, M4-BE-03, M3-AI-09 | Ngày 3–5 |
| M4-BE-05 | Implement `POST /api/v1/query` tích hợp pipeline | [AI Dev] | Endpoint nhận QueryRequest, gọi pipeline, trả QueryResponse; pass `curl` test | M4-BE-01, M4-BE-04 | Ngày 5–6 |
| M4-BE-06 | Implement `GET /api/v1/health` (health check) | [AI Dev] | JSON: database status, llm_server status, api version | M4-BE-02, M4-BE-03 | Ngày 6 |
| M4-WEB-01 | Khởi tạo React project (Vite + Bootstrap 5) | [AI Dev] | App chạy `localhost:5173`, folder match docs spec | — | Ngày 1 |
| M4-WEB-02 | Build `ChatInterface`: input bar + message list | [AI Dev] | User input → message bubble; loading spinner; auto-scroll | M4-WEB-01 | Ngày 2–3 |
| M4-WEB-03 | Build `ResponseRenderer` + `TableRenderer` | [AI Dev] | Switch `response_type`; Bootstrap table responsive | M4-WEB-01 | Ngày 3–4 |
| M4-WEB-04 | Build `TextRenderer` + `WarningRenderer` | [AI Dev] | Chat bubble style; Alert variant="danger" + icon | M4-WEB-01 | Ngày 4–5 |
| M4-WEB-05 | Build `apiService.js`: Axios client kết nối Backend | [AI Dev] | `POST /api/v1/query`, error handling, env-based API_BASE_URL | M4-BE-05, M4-WEB-01 | Ngày 6–7 |

### Cả 2 Đội

| Task ID | Tên Công việc | Assignee | DoD | Deps | Ngày target |
|---|---|---|---|---|---|
| M4-WEB-06 | 🤝 Integration test: Web → Backend → LLM → AuraDB (full round-trip) | [AI Dev] + [Data Dev] | 5 câu end-to-end: ≥1 table, ≥1 text, ≥1 warning hiển thị đúng | M4-BE-05, M4-WEB-05 | Ngày 8–10 |

### 📊 Tổng kết Sprint 2

| Assignee | Số tasks | Trọng tâm |
|---|---|---|
| [Data Lead] | 2 | `graph_service.py`, `/schema` endpoint |
| [Data Dev] | 1 (hỗ trợ) | Integration test (verify DB queries) |
| [AI Lead] | 2 | `llm_service.py`, `pipeline.py` (Orchestrator) |
| [AI Dev] | 9 | Pydantic models, API endpoints, toàn bộ React components |

### ⚠️ Critical Path — Sprint 2
```
Song song 2 luồng:

LUỒNG BACKEND:                          LUỒNG FRONTEND:
[AI Dev] Pydantic models (Ngày 1–2)     [AI Dev] React project (Ngày 1)
[Data Lead] graph_service (Ngày 1–3)     [AI Dev] ChatInterface (Ngày 2–3)
[AI Lead] llm_service (Ngày 1–3)         [AI Dev] Renderers (Ngày 3–5)
        ↓                                        ↓
[AI Lead] pipeline.py (Ngày 3–5)         [AI Dev] apiService (Ngày 6–7)
[AI Dev] /query endpoint (Ngày 5–6)              ↓
        ↓                                        ↓
        └──────── 🤝 INTEGRATION ────────────────┘
                   (Ngày 8–10)
```

> **Lưu ý cân bằng tải**: [AI Dev] rất nặng Sprint này (9 tasks). Giải pháp:
> - [Data Dev] hỗ trợ viết React components (TableRenderer, TextRenderer) sau khi ETL đã xong từ Sprint 1
> - [Data Lead] có thể hỗ trợ viết `apiService.js` vì đã hiểu API contract từ `graph_service.py`

### 🤝 Điểm bắt tay cuối Sprint 2
- **[Data Lead]** cung cấp `graph_service.py` hoàn chỉnh → **[AI Lead]** tích hợp vào `pipeline.py`
- **[AI Dev]** + **[Data Dev]** cùng chạy integration test
- **Demo cuối Sprint 2**: MVP end-to-end — hỏi trên browser → nhận câu trả lời

---

## Bảng Tổng hợp 3 Sprints — Workload theo Người

| Assignee | Sprint 0 | Sprint 1 | Sprint 2 | Tổng 3 sprints |
|---|---|---|---|---|
| **[Data Lead]** | 3 tasks | 4 tasks | 2 tasks | **9 tasks** |
| **[Data Dev]** | 5 tasks | 3 tasks | 1 task (hỗ trợ) | **9 tasks** |
| **[AI Lead]** | 3 tasks | 3 tasks | 2 tasks | **8 tasks** |
| **[AI Dev]** | 3 tasks | 3 tasks | 9 tasks | **15 tasks** |
| **Cả 4** | 2 tasks | — | 1 task | **3 tasks** |

> ⚠️ **[AI Dev]** nặng đột biến ở Sprint 2 → cần hỗ trợ từ **[Data Dev]** cho frontend.

---

## Checklist Sprint Ceremonies

Mỗi Sprint 2 tuần, team thực hiện:

- [ ] **Thứ 2, Tuần đầu**: Sprint Planning (1h) — review backlog, chia task, thống nhất mục tiêu
- [ ] **Hàng ngày**: Daily Sync (15 phút async trên Discord `#daily-sync`)
- [ ] **Thứ 6, Tuần đầu**: Mid-sprint Check (30 phút) — kiểm tra progress, điều chỉnh
- [ ] **Thứ 6, Tuần hai**: Sprint Review (1h) — demo kết quả, cross-review
- [ ] **Sau Review**: Sprint Retro (30 phút) — tốt? cần cải thiện?
