# Refactor: Cypher path — tách concern, sửa template, bỏ count

**Trạng thái: PHIÊN 1 ✅ PHIÊN 2 ✅ PHIÊN 3 ✅ PHIÊN 4 ✅ hoàn thành — đang ở PHIÊN 5**

> Làm theo từng **PHIÊN**. Mỗi phiên độc lập, hệ thống vẫn chạy được sau mỗi phiên.
> Sau mỗi phiên: tick checkbox `[x]`, cập nhật dòng "Trạng thái" ở trên, commit, dừng hỏi ý.
> Commit message mẫu: `refactor(cypher): PHIÊN n — <mô tả ngắn>`.

---

## Kiến trúc mục tiêu (3 tầng)

```
TRANSPORT:  llm_provider.py              # get_chat_client() / get_embedding_client() — lazy singleton
USE-CASE:   cypher_query_builder.py      # template + LLM fallback (GỘP, giữ tên)
            cypher_answer_synthesizer.py  # KG records → NL (mới)
            lightrag_llm_adapter.py       # adapter LightRAG (ĐỔI TÊN từ llm_service.py)
FACADE:     cypher_graph_service.py      # đường Cypher (mới) — query()
            lightrag_service.py           # đường LightRAG (giữ)
ROUTER:     pipeline.py                  # router thuần, gọi 2 facade
```

Quy ước tên: tiền tố `cypher_*`/`lightrag_*` = thuộc một đường;
`llm_provider` = transport trung lập; `_service` = facade; `_adapter` = lớp khớp signature thư viện ngoài.

---

## Checklist thực hiện tuần tự

### PHIÊN 1 — Fix bug Cypher `exact` ✦ ĐANG LÀM
> Nhỏ, giá trị cao, rủi ro thấp. Đây là bug nghiêm trọng nhất: mọi truy vấn exact đều fallback LightRAG.

**Vấn đề:** `_tiered_where()` nhánh `exact=True` trả `WHERE alias.disease_name = $name` không có `WITH`,
khiến template ghép `{wf}LIMIT $limit` thành Cypher không hợp lệ (`LIMIT` phải là sub-clause của `WITH`/`RETURN`).
Hệ quả: Neo4j ném lỗi → pipeline nuốt lỗi → **âm thầm fallback LightRAG mọi lúc với query exact**.

**Fix tại** `ai_engine/services/cypher_query_builder.py:24`:
```python
# TRƯỚC (sai):
if exact:
    return f"WHERE {alias}.disease_name = $name\n        "

# SAU (đúng):
carry_str = "".join(f", {v}" for v in carry)
if exact:
    return (
        f"WHERE {alias}.disease_name = $name\n"
        f"        WITH {alias}{carry_str}\n"
        f"        "
    )
```

- [x] Sửa `_tiered_where()` như trên. Không đụng `_tmpl_*` vì tất cả đi qua helper này.
- [x] Verify: kiểm tra output tất cả 8 forward template exact → WITH xuất hiện trước LIMIT, cú pháp hợp lệ.
- [x] Commit: `fix(cypher): add WITH before LIMIT in exact-match templates`.

---

### PHIÊN 2 — Bỏ `count` / `count_by_type`, định tuyến về ví dụ tiêu biểu
> Câu hỏi đếm/liệt kê không có câu trả lời chính xác trong bài toán y khoa → trả ví dụ tiêu biểu.
> Template `count` hiện đang đếm toàn DB, bỏ qua entity ("viêm phổi").

- [x] `cypher_query_builder.py`: xoá `_tmpl_count`, `_tmpl_count_by_type` + 2 entry trong dict `builders`.
- [x] `query_router.py`: xoá `COUNT_PATTERNS` + vòng nhận diện count; xoá `"count"` khỏi `_VALID_QUERY_TYPES`;
  xoá mô tả + few-shot count trong `_INTENT_SYSTEM_PROMPT`; cập nhật docstring.
- [x] `query_router.py`: thêm regex + few-shot LLM: câu đếm/liệt kê → `find_by_symptom`/`symptoms` (ví dụ tiêu biểu, không trả số).
- [x] `pipeline.py`: xoá Step 5 count; đổi `if entity is None and query_type != "count":` → `if entity is None:`;
  xoá nhánh `count` trong `_extract_structured_data`.
- [x] Verify: routing "có bao nhiêu bệnh có triệu chứng ho khan" → `find_by_symptom/ho khan`; "có bao nhiêu triệu chứng của viêm phổi" → `symptoms/viêm phổi`; `build_cypher_query('count',...)` → `None`. Grep sạch.
- [x] Commit: `refactor(router): remove count query_type, route counting to representative examples`.

---

### PHIÊN 3 — Tầng transport `llm_provider.py` + đổi tên adapter LightRAG
> Tách "dựng client" ra khỏi "dùng client" để Cypher path và LightRAG path không phụ thuộc lẫn nhau.

- [x] Tạo `ai_engine/services/llm_provider.py`: `get_chat_client()`, `get_embedding_client()` lazy singleton,
  đọc `ai_engine.config` (không đọc `os.environ`).
- [x] Đổi tên `llm_service.py` → `lightrag_llm_adapter.py`; sửa `_get_llm_client()/_get_embedding_client()`
  ủy quyền cho `llm_provider`. Giữ nguyên `llm_model_func`, `embedding_func`, health check.
- [x] Cập nhật mọi import `ai_engine.services.llm_service` → `...lightrag_llm_adapter`
  (`lightrag_service.py`, health check, `main`, tests).
- [x] Verify: `pytest`; health check LLM + 1 query LightRAG → hành vi không đổi.
- [x] Commit: `refactor(llm): extract llm_provider transport, rename llm_service → lightrag_llm_adapter`.

---

### PHIÊN 4 — Tách synthesizer ra `cypher_answer_synthesizer.py`
> `text2cypher.py` hiện chứa cả "sinh Cypher" lẫn "tạo câu trả lời end-user" — vi phạm SRP.
> Phiên này tách phần synthesizer, `text2cypher.py` tạm giữ (chưa xoá).

- [x] Tạo `ai_engine/services/cypher_answer_synthesizer.py`: chuyển `synthesize_answer` + toàn bộ helper
  (`_prepare_records_for_llm`, `_KEY_LABELS`, `_BLOB_FIELDS`, `_clean_category`, `_split_blob`,
  `_strip_trailing_commentary`, `_TRAILING_JUNK_*`, `_MAX_*`) từ `text2cypher.py`; dùng `llm_provider.get_chat_client()`.
- [x] Thêm rule liệt kê/đếm vào `system_prompt`:
  "TUYỆT ĐỐI không nêu tổng số. Câu đếm/liệt kê → chỉ nêu một số ví dụ, mở đầu 'Một số ... tiêu biểu là:'."
- [x] Sửa nhánh `except synthesize_answer`: thay `return str(records[:3])` bằng câu an toàn + log ERROR.
- [x] Verify: import module mới thành công; `pytest` xanh.
- [x] Commit: `refactor(cypher): extract cypher_answer_synthesizer with no-count rule + safe fallback`.

---

### PHIÊN 5 — Gộp sinh Cypher vào builder + facade `cypher_graph_service.py`
> Gộp `generate_cypher` + `SCHEMA_PROMPT` vào `cypher_query_builder.py`; tạo facade symmetric LightRAG.

- [ ] `cypher_query_builder.py`: hấp thụ `generate_cypher` + `SCHEMA_PROMPT` từ `text2cypher.py`
  (xoá few-shot count + mệnh đề "(except count queries)" trong SCHEMA_PROMPT);
  thêm `async def to_cypher(query_type, entity, exact, question) -> tuple[str, dict, bool]`;
  dùng `llm_provider.get_chat_client()`.
- [ ] Tạo `ai_engine/services/cypher_graph_service.py`: `async def query(...) -> dict`
  đóng gói `to_cypher → validate_cypher → sanitize_cypher → execute_cypher → synthesize_answer`.
  Trả: `{success, answer, records, cypher, used_template}` hoặc `{success:False, fallback:True, reason}`
  hoặc `{success:False, fallback:False, error_code:"CYPHER_GENERATION_FAILED"}`.
- [ ] Verify: unit test `to_cypher()` (template hit + LLM fallback) và `cypher_graph_service.query()` xanh.
- [ ] Commit: `refactor(cypher): merge text2cypher into builder + add cypher_graph_service facade`.

---

### PHIÊN 6 — Đấu nối pipeline + xoá `text2cypher.py`
> Phiên cuối: kết nối facade vào pipeline, dọn dẹp module cũ.

- [ ] `pipeline.py`: `_execute_cypher_path` → router mỏng gọi `cypher_graph_service.query(...)`;
  xử lý `fallback`/`error_code`/success; bỏ leak `str(records[:3])`.
- [ ] `query_router.py:464`: `from ai_engine.services.llm_provider import get_chat_client`
  (thay `from ...text2cypher import client`).
- [ ] Xoá `ai_engine/services/text2cypher.py`. Grep xác nhận không còn import `text2cypher` ở đâu.
- [ ] Cập nhật tests tham chiếu cũ (`text2cypher` / `synthesize_answer` / `client` / `llm_service`).
- [ ] Verify: `ruff check .` sạch; `pytest` xanh; gọi API:
  - "tiểu đường có triệu chứng gì" → Cypher path (exact), không fallback LightRAG.
  - "có bao nhiêu bệnh có triệu chứng ho khan" → "Một số bệnh ... tiêu biểu là: ...", không có số tổng.
  - "có bao nhiêu triệu chứng của viêm phổi" → liệt kê ví dụ, không trả số node DB.
  - Ép synthesize lỗi → câu an toàn, không lộ repr record thô.
- [ ] Commit: `refactor(pipeline): route cypher path through facade, remove text2cypher`.
