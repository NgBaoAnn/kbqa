# AI Engine

Module `ai_engine/` chứa toàn bộ logic AI, tách biệt khỏi backend HTTP layer.

## Cấu trúc

```
ai_engine/
├── config.py                    # LLM, Embedding, Neo4j, LightRAG settings
├── services/
│   ├── query_router.py          # Intent extraction (LLM + Regex)
│   ├── cypher_query_builder.py  # Sinh Cypher từ query_type + entity
│   ├── cypher_graph_service.py  # Facade: build Cypher → execute → synthesize
│   ├── cypher_answer_synthesizer.py  # Format kết quả Cypher → NL
│   ├── intent_classifier.py     # (Legacy) simple classifier
│   ├── lightrag_service.py      # LightRAG wrapper (query, stream)
│   ├── lightrag_llm_adapter.py  # Adapter: Ollama → LightRAG interface
│   ├── llm_provider.py          # OpenAI-compatible client factory
│   ├── indexing_service.py      # Document indexing vào LightRAG
│   └── query_router.py          # Query Router chính
├── prompts/
│   └── text_to_cypher.md        # Prompt template cho Cypher generation
├── eval/                        # Benchmark & evaluation
│   ├── golden_test_set.json     # 50+ test cases
│   ├── eval_golden_test.py      # Golden test runner
│   ├── run_benchmark.py         # Multi-model benchmark
│   └── score_golden.py          # Scoring utilities
└── utils/
    └── response_formatter.py    # Chuẩn hóa response format
```

## Query Router — Luồng phân loại câu hỏi

```
Câu hỏi NL
    │
    ▼
1. LLM Structured Extraction
   (extract_intent_with_llm)
   → JSON { query_type, entity }
    │
    ▼ (nếu LLM fail hoặc entity=null)
2. Regex Fallback
   (classify_cypher_intent)
   → Pattern matching tiếng Việt + Anh
    │
    ▼
3. Pipeline Routing
   - find_by_* types → CYPHER (reverse query, CONTAINS match)
   - entity=null → LIGHTRAG
   - entity in KG → CYPHER (exact match)
   - entity not in KG → LIGHTRAG (data-driven fallback)
   - Nhiều bệnh trùng tên → disambiguation response
```

## Cypher Path

1. **cypher_query_builder.py**: Tạo Cypher query từ `(query_type, entity)`. Có 2 chế độ:
   - **Template mode**: Dùng template Cypher cho từng query_type (nhanh, deterministic)
   - **LLM mode**: LLM sinh Cypher tự do (cho câu hỏi phức tạp)

2. **cypher_answer_synthesizer.py**: Lấy records từ Neo4j → format thành câu trả lời NL bằng LLM.

3. **Fallback**: Nếu Cypher trả 0 records → tự động chuyển sang LightRAG.

## LightRAG Path

1. **lightrag_service.py**: Wrapper quanh thư viện `lightrag-hku`.
   - Query modes: `naive` (vector search only), `local` (entity + rel search), `mix`, `hybrid`
   - Sử dụng Qdrant Cloud cho 3 collections: `lightrag_vdb_entities`, `lightrag_vdb_relationships`, `lightrag_vdb_chunks`

2. **lightrag_llm_adapter.py**: Bridge Ollama API → LightRAG's expected interface.

## LLM Configuration

| Biến | Default | Mô tả |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL_NAME` | `qwen2.5:14b` | Model cho intent extraction + synthesis |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model |
| `EMBEDDING_DIM` | `1024` | Embedding dimension |
| `DEFAULT_QUERY_MODE` | `naive` | LightRAG default mode |
| `FORCE_LIGHTRAG_NAIVE_MODE` | `true` | Bắt buộc naive mode (khi chưa có LightRAG internal graph) |

## Evaluation

```bash
# Chạy golden test set
python ai_engine/eval/eval_golden_test.py

# Multi-model benchmark
python ai_engine/eval/run_benchmark.py
```

Golden test set: `ai_engine/eval/golden_test_set.json` — 50+ câu hỏi cover mọi query_type.
