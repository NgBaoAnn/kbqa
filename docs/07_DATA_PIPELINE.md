# Data Pipeline

## Nguồn dữ liệu

**VietMedKG** (HySonLab, ACM TALLIP 2025) — Knowledge Graph y tế tiếng Việt.

- File gốc: `data/preprocessed_data.csv` (~63MB, ~4000 bệnh)
- Mỗi row = 1 bệnh với đầy đủ thuộc tính

## Luồng ETL

```
CSV (preprocessed_data.csv)
    │
    ▼
etl/graph_builder/build_graph.py    ← Import VietMedKG schema
    │
    ▼
Neo4j AuraDB
├── :Disease  (disease_name, description, category, cause)
├── :Symptom  (disease_symptom, check_method, people_easy_get)
├── :Treatment (cure_method, cure_department, cure_probability)
├── :Medicine  (drug_common, drug_detail, drug_recommend)
├── :Advice    (nutrition_do_eat, nutrition_not_eat, disease_prevention)
└── Relationships: HAS_SYMPTOM, HAS_TREATMENT, IS_PRESCRIBED, HAS_ADVICE, IS_LINKED_WITH
```

## Import VietMedKG → Neo4j

```bash
# Dry run (chỉ kiểm tra)
python etl/graph_builder/build_graph.py --dry-run

# Import thực tế
python etl/graph_builder/build_graph.py --batch-size 500

# Xóa graph cũ trước khi import
python etl/graph_builder/build_graph.py --clear --batch-size 500
```

Script thực hiện:
1. Tạo uniqueness constraints
2. Import Disease nodes
3. Import Symptom nodes + `HAS_SYMPTOM` relationships
4. Import Treatment nodes + `HAS_TREATMENT`
5. Import Medicine nodes + `IS_PRESCRIBED`
6. Import Advice nodes + `HAS_ADVICE`
7. Import `IS_LINKED_WITH` (associated diseases)
8. Validate graph (node/relationship counts)

## LightRAG Entities → Neo4j

Script `scripts/ingest_to_neo4j.py` đồng bộ LightRAG entities + relationships từ **Qdrant** sang **Neo4j** (label `:base`):

```bash
python scripts/ingest_to_neo4j.py
```

- Đọc ~34,955 entities + ~48,125 relationships từ Qdrant
- MERGE vào Neo4j (idempotent — chạy lại an toàn)
- Label `:base` tách biệt với VietMedKG schema (`:Disease`, `:Symptom`...)

Cần thiết khi muốn dùng LightRAG mode `local` / `mix` / `global` (thay vì `naive`).

## Supabase Database Schema

App data lưu trong Supabase Postgres:

| Table | Mô tả |
|---|---|
| `user_profiles` | User profile (role, is_active, display_name) |
| `conversations` | Chat conversations |
| `messages` | Chat messages (user + assistant) |
| `feedback` | User feedback (up/down + reason) |
| `review_items` | Review queue items (từ negative feedback) |
| `user_preferences` | User settings (language, style) |
| `query_logs` | Pipeline execution logs |

Migrations: `backend/migrations/supabase/versions/`
