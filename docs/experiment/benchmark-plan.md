# Plan (checklist): Benchmark AegisHealth trên Kaggle — 3 kịch bản ablation

**Trạng thái: PHASE 1 ✅ PHASE 2 ✅ — đang ở PHASE 3**
> Mỗi PHASE độc lập, có thể dừng/tiếp xuyên phiên. Sau mỗi PHASE: tick `[x]`, cập nhật dòng "Trạng thái",
> commit (nếu là code), rồi có thể dừng.
> Đây là **nguồn chân lý tiến độ** trong repo. Đọc dòng "Trạng thái" + checkbox để biết đang ở đâu.

---

## Context & Mục tiêu

Chứng minh **Hybrid GraphRAG của AegisHealth giảm hallucination** cho QA y tế, qua **ablation 3 bậc**:
LLM thuần → +RAG vector → +KG. Tài nguyên giới hạn → chạy trên Kaggle (GPU T4), 3 notebook riêng biệt.

## Quyết định đã CHỐT (không mở lại)

| # | Quyết định |
|---|---|
| D1 | **Rebuild** benchmark → `golden_test_v2.json` (không dùng tập cũ). |
| D2 | Chỉ giữ question_type **ENTITY-SET**; loại free-text (mô tả/nguyên nhân/phòng tránh/drug_detail) + outlier (loại/khoa/tỉ_lệ). |
| D3 | **CARD_CAP = 20** đáp án/câu; **N ≈ 100** câu stratified; seed=42. |
| D4 | Metric **chủ đạo** = entity-set: **Fabrication rate ★ + Precision ★ + Recall + F1**, tách **regime** (single→EM/Hits@1, multi→P/R/F1). |
| D5 | Mention extraction **deterministic** (match `gold ∪ KG_ENTITIES` bằng substring, longest-match) — không bắt buộc LLM. |
| D6 | Metric **phụ** = **BERTScore** (đa ngôn ngữ). Bỏ BLEU/METEOR (chỉ thêm nếu hội đồng yêu cầu, kèm caveat). |
| D7 | **3 notebook riêng biệt** (baseline / lightrag-naive / hybrid). |
| D8 | Data bị `.gitignore` → ship `golden_test_v2.json` + `kg_entities.txt` (~2MB) qua **Kaggle Dataset** `aegishealth-benchmark`. Rebuild chạy **local**, notebook KHÔNG cần `triples.json` 76MB. |
| D9 | Notebook gọi `run_pipeline` **in-process** (bỏ uvicorn) để đơn giản + tránh chờ backend 240s. |

## Cảnh báo kỹ thuật (đã tính trong plan)

- **Embedding bắt buộc `bge-m3` (1024d)** — KHÔNG `nomic-embed-text` (768d) như notebook cũ, vì Qdrant ingest bằng bge-m3.
- **Synthesizer cố ý cắt list** (`_MAX_RECORDS=5`, `_MAX_LIST_ITEMS=15`, rule "ví dụ tiêu biểu") → Recall thấp là *do thiết kế*; vì vậy metric chính là Precision/Fabrication (robust với truncation).
- **Secrets**: lấy qua `kaggle_secrets`; `.env` repo đang chứa credential thật → nên rotate.
- **Internet On + GPU T4** bắt buộc cho N2/N3.

---

## PHASE 0 — Persist plan (cross-session) ✅
- [x] Tạo `docs/experiment/benchmark-plan.md` = copy checklist này (nguồn chân lý tiến độ trong repo).
- [x] Cập nhật memory: thêm file `experiment_benchmark.md` + dòng index trong `MEMORY.md` trỏ tới doc trên.
- [x] Commit: `docs(experiment): add Kaggle benchmark plan checklist`.

## PHASE 1 — Rebuild dataset (LOCAL, deterministic) ✅
- [x] Viết `etl/benchmark_gen/rebuild_golden.py`:
  - [x] Load `1hop.json`+`2hop.json`; gắn `complexity` (hop) + `direction` (forward/reverse).
  - [x] Whitelist ENTITY-SET type (D2); filter CARD_CAP=20; gắn `regime` (single/multi).
  - [x] Stratified sample N=100 theo `(complexity × direction × regime)`, seed=42.
  - [x] Enrich record: `{question, question_type, answer, complexity, direction, regime, answer_cardinality}`.
  - [x] Build `KG_ENTITIES` = `headers ∪ tails-entity-relation` (split blob comma, 65553 entities).
- [x] Output: `data/benchmark/golden_test_v2.json` (100 Q), `golden_test_v2_stats.md`, `kg_entities.txt`.
- [x] Verify: 100 câu, mọi `cardinality ≤ 20`, không còn free-text/outlier; 6 strata.
- [x] Commit: `feat(benchmark): add rebuild_golden.py for stratified entity-set golden_test_v2`.
> Note: Data-consistency Cypher spot-check (Neo4j live) → để thực hiện khi có kết nối Neo4j.

## PHASE 2 — Scorer `ai_engine/eval/score_golden.py` ✅
- [x] `normalize(s)` (NFC, lowercase, strip); load `KG_ENTITIES`.
- [x] Mention extraction deterministic: bold phrases + bullets + pipes (strip `**` from list items).
- [x] Metric chủ đạo (D4): fabrication rate, precision, recall, F1, off-answer rate, EM/Hits@1.
- [x] Metric phụ (D6): BERTScore optional (`--bertscore` flag, falls back gracefully).
- [x] `score_run(raw_jsonl, golden, kg) -> report` + breakdown by regime/complexity/type.
- [x] 5 unit tests + integration test (đúng/bịa/prose/single/KG-vocab) — tất cả pass.
- [x] Commit: `feat(eval): add hallucination scorer score_golden`.

## PHASE 3 — Ship data lên Kaggle
- [ ] Tạo Kaggle Dataset `aegishealth-benchmark` chứa `golden_test_v2.json` + `kg_entities.txt`.
- [ ] (Không commit data vào git — giữ quy ước `.gitignore`.)

## PHASE 4 — Notebook 1 `kaggle_eval_1_baseline.ipynb` (LLM thuần)
- [ ] Setup: GPU T4, Internet On, attach dataset. Chỉ cần Ollama + qwen2.5:3b (không Neo4j/Qdrant/bge-m3).
- [ ] Inference: mỗi câu gọi thẳng `AsyncOpenAI` (closed-book medical prompt), KHÔNG `run_pipeline`.
- [ ] Ghi `raw_baseline.jsonl` → `score_run` → `results_baseline.json` + `report_baseline.md`.

## PHASE 5 — Notebook 2 `kaggle_eval_2_lightrag_naive.ipynb` (RAG vector)
- [ ] Setup: + bge-m3 + Qdrant secrets; `DISABLE_CYPHER_PATH=true`, `LIGHTRAG_KG_STORAGE` non-Neo4j, `FORCE_LIGHTRAG_NAIVE_MODE=false`.
- [ ] Inference: `await run_pipeline(q, mode="naive")` (ép LightRAG, bypass Cypher).
- [ ] Tiền đề: Qdrant collections đã ingest (xác nhận smoke test). Ghi `raw_lightrag.jsonl` → score → report.

## PHASE 6 — Notebook 3 `kaggle_eval_3_hybrid.ipynb` (Cypher + LightRAG)
- [ ] **Kaggle UI**: GPU T4 ×1, Internet On; Secrets `NEO4J_URI/USERNAME/PASSWORD`, `QDRANT_URL/API_KEY`; attach dataset.
- [ ] Cells (tái dùng `kaggle_benchmark.ipynb`, sửa 3 điểm):
  - [ ] **#1** pull `qwen2.5:3b` **+ `bge-m3`** (không nomic-embed-text).
  - [ ] **#2** `.env`: `EMBEDDING_MODEL=bge-m3`, `EMBEDDING_DIM=1024`, `LIGHTRAG_VECTOR_STORAGE=QdrantVectorDBStorage`, `LIGHTRAG_KG_STORAGE=Neo4JStorage`, `FORCE_LIGHTRAG_NAIVE_MODE=false`, `DISABLE_CYPHER_PATH=false`, `DEFAULT_QUERY_MODE=mix`.
  - [ ] **#3** in-process: set `sys.path += [REPO_DIR, REPO_DIR/backend]` + `os.environ` TRƯỚC import, rồi `from app.services.pipeline import run_pipeline`.
- [ ] Smoke 1 câu → xác nhận có câu `engine=cypher_direct`.
- [ ] Inference `await run_pipeline(q)` (mode=None, router đầy đủ); lưu thêm `engine`+`query_mode`.
- [ ] Ghi `raw_hybrid.jsonl` → score → report; vẽ **routing distribution** (cypher vs lightrag).

## PHASE 7 — Tổng hợp & kết luận
- [ ] Gộp 3 `results_*.json` → bảng so sánh + biểu đồ.
- [ ] **Sanity ablation**: fabrication(N1) > fabrication(N2) ≥ fabrication(N3) & precision tăng dần. Nếu ngược → debug embedding/secrets/routing.
- [ ] So khớp số câu 3 file; tỉ lệ `TIMEOUT`/`MODEL_UNAVAILABLE` thấp.
- [ ] Viết kết luận: con số headline = **fabrication rate giảm** qua 3 bậc → luận điểm "GraphRAG giảm hallucination".

---

## Bảng file (tạo/sửa)

| File | Hành động |
|---|---|
| `docs/experiment/benchmark-plan.md` | MỚI — checklist tiến độ trong repo (PHASE 0). |
| `etl/benchmark_gen/rebuild_golden.py` | MỚI — rebuild + build KG_ENTITIES (PHASE 1). |
| `data/benchmark/{golden_test_v2.json, golden_test_v2_stats.md, kg_entities.txt}` | MỚI (output, gitignored). |
| `ai_engine/eval/score_golden.py` | MỚI — scorer dùng chung 3 notebook (PHASE 2). |
| `notebooks/kaggle_eval_{1_baseline,2_lightrag_naive,3_hybrid}.ipynb` | MỚI (PHASE 4–6). |
| `backend/app/services/pipeline.py::run_pipeline` | tái dùng in-process, không sửa. |
| (tham khảo) `notebooks/kaggle_benchmark.ipynb`, `etl/benchmark_gen/make_*.py`, `ai_engine/eval/eval_golden_test.py` | mượn pattern. |

## Ngân sách Kaggle (T4, ~12h/session, 30h GPU/tuần)
N1 ~15–25′ · N2 ~15–30′ · N3 ~25–45′ → 3 phiên thừa quota.
