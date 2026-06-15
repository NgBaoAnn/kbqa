# AegisHealth KBQA — Tổng quan

> Hệ thống Hỏi–Đáp Y tế bằng Ngôn ngữ Tự nhiên, sử dụng Hybrid GraphRAG (LightRAG + Cypher) trên Knowledge Graph VietMedKG.

## Mục tiêu

Cho phép người dùng **hỏi câu hỏi y tế bằng tiếng Việt** (hoặc Anh) và nhận câu trả lời chính xác, có nguồn gốc từ đồ thị tri thức — thay vì chỉ dựa vào LLM.

## Kiến trúc Hybrid (Phương án C)

```
Câu hỏi NL  ──▶  Query Router
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
   Cypher Path              LightRAG Path
   (Neo4j trực tiếp)        (Semantic retrieval)
   - Tra cứu chính xác      - Câu hỏi mơ hồ/tổng hợp
   - ~50-100ms               - Entity + Relationship search
   - Deterministic            - LLM synthesis
        │                       │
        └───────────┬───────────┘
                    ▼
              API Response
```

**Auto Fallback**: Cypher trả 0 kết quả → tự động chuyển LightRAG.

## Tech Stack

| Layer | Công nghệ |
|---|---|
| Backend API | FastAPI (Python 3.11+) |
| Frontend | React 19 + Vite + TypeScript |
| Knowledge Graph | Neo4j AuraDB (VietMedKG) |
| Semantic Retrieval | LightRAG + Qdrant (bge-m3 embeddings) |
| LLM | Ollama / vLLM (OpenAI-compatible API) |
| Auth | Supabase Auth (JWT) |
| App Database | Supabase Postgres (conversations, feedback, logs) |
| Deployment | EC2 + Docker |

## Graph Schema (VietMedKG)

```
(Disease) ──HAS_SYMPTOM──▶ (Symptom)
(Disease) ──HAS_TREATMENT──▶ (Treatment)
(Disease) ──IS_PRESCRIBED──▶ (Medicine)
(Disease) ──HAS_ADVICE──▶ (Advice)
(Disease) ──IS_LINKED_WITH──▶ (Disease)
```

Dữ liệu gốc: CSV ~63MB → ~4000 bệnh, import bằng `etl/graph_builder/build_graph.py`.

## Người dùng mục tiêu

- **Người dùng phổ thông**: Tra cứu thông tin y tế qua chat
- **Sinh viên Y khoa**: Tra cứu quan hệ bệnh–thuốc–triệu chứng
- **Admin / Reviewer**: Giám sát chất lượng, xem review queue

> ⚠️ Hệ thống chỉ mang tính chất tham khảo, không thay thế tư vấn y khoa chuyên nghiệp.
