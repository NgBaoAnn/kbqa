Plan — Hybrid Routing v2 (Reverse Queries + KG-driven LLM Prompt + Honest Logging)

 Status — Phase 1–4 đã DONE

 Đợt trước đã implement và pass test:
 - P1 Vá regex (R1/R2/R3) trong ai_engine/services/query_router.py:_clean_entity + đổi thứ tự pattern
 symptoms.
 - P2 Thêm extract_intent_with_llm() (JSON output, Ollama Qwen2.5).
 - P3 Pipeline data-driven routing (backend/app/services/pipeline.py:_run_pipeline_inner).
 - P4 Try/except cho _disambiguate_entity (R6).

 Context — Phát hiện qua user test

 Câu test: "Việc tránh ăn [Dưa chua khô, Bia, Rượu trắng, Trứng cút] có thể hỗ trợ điều trị bệnh lý nào?"

 Log thực tế:
 [INFO] LLM intent: type=treatment entity=None
 [INFO] Pipeline: intent type=treatment entity=None method=regex
 [INFO] No entity extracted → LightRAG (method=regex)

 Ba vấn đề + dữ liệu KG cho thấy có thể trả lời được:
 1. Log sai: LLM đã được gọi nhưng routing_method vẫn báo regex.
 2. LLM misclassify: câu đảo chiều ("avoid X → which disease") bị quy về treatment vì prompt LLM không có
 nhãn cho reverse query.
 3. KG thực sự có dữ liệu: sample từ data/processed/preprocessed_data.csv cho thấy Advice.nutrition_not_eat
 chứa chuỗi comma-separated như "Rượu trắng, Bia, Trứng vịt muối, Dưa chua khô" (trùng khớp 100% với câu test
  của user). Nếu wire find_by_nutrition_avoid thì Cypher WHERE toLower(a.nutrition_not_eat) CONTAINS
 toLower('dưa chua khô') sẽ trả về bệnh đúng — không cần LightRAG.

 Files to Modify

 - ai_engine/services/query_router.py — full rewrite _INTENT_SYSTEM_PROMPT, mở rộng _VALID_QUERY_TYPES, thêm
 regex pattern cho 5 reverse type, thêm module docstring giải thích thuật toán.
 - ai_engine/services/cypher_query_builder.py — thêm 4 reverse template (find_by_medicine,
 find_by_nutrition_avoid, find_by_nutrition_eat, find_by_prevention) + formatter; find_by_symptom đã có sẵn.
 - backend/app/services/pipeline.py — sửa cập nhật routing_method; thêm nhánh skip-disambiguation cho
 _FIND_BY_TYPES; mở rộng table-layout list.

 Cách xác định (query_type, entity) — tài liệu hóa thuật toán

 (Sẽ chèn thành module-level docstring vào query_router.py.)

 ĐẦU VÀO: câu hỏi tự nhiên (Việt / Anh)

 BƯỚC 1 — regex fast path (classify_cypher_intent)
   ┌─ COUNT_PATTERNS match           → ("count", None)
   ├─ FORWARD pattern match          → (forward_type, _clean_entity(group(1)))
   │     forward_type ∈ {symptoms, medicine, treatment, advice,
   │                     prevention, department, profile}
   ├─ REVERSE pattern match          → (reverse_type, _clean_entity(group(1)))
   │     reverse_type ∈ {find_by_symptom, find_by_medicine,
   │                     find_by_nutrition_avoid, find_by_nutrition_eat,
   │                     find_by_prevention}
   └─ Không match                    → (None, None)

   _clean_entity loại:
     - Tiền tố "bệnh "/"bị "
     - Đuôi "không"/"như thế nào"/"thế nào"/"là gì"/"gồm gì"/"thì sao"
     - Bare question words (gì, nào, sao, what, which, …)
     - Chuỗi < 2 ký tự

 BƯỚC 2 — LLM fallback (chỉ khi entity is None & query_type != "count")
   extract_intent_with_llm → JSON {"query_type": ..., "entity": ...}
   Validate vs _VALID_QUERY_TYPES; entity chạy lại _clean_entity.

 BƯỚC 3 — Routing trong pipeline
   query_type == "count"             → CYPHER (no entity)
   query_type ∈ _FIND_BY_TYPES       → CYPHER (entity là keyword, CONTAINS, KHÔNG disambiguate)
   entity is None (forward)          → LIGHTRAG (không xác định được bệnh)
   entity có trong KG                → CYPHER (exact=True sau disambiguation)
   entity không có trong KG          → LIGHTRAG (data-driven fallback)

 Phase 5 — Honest routing_method logging (pipeline.py)

 Trong _run_pipeline_inner:

 if entity is None and query_type != "count":
     q_type_llm, entity_llm = await extract_intent_with_llm(question)
     if q_type_llm:
         query_type = q_type_llm
     if entity_llm:
         entity = entity_llm
     routing_method = "llm"   # LLM đã được gọi → ghi nhận trung thực

 (Khi regex tìm được entity → không vào nhánh này → routing_method vẫn "regex" — đúng.)

 Phase 6 — Full _INTENT_SYSTEM_PROMPT (query_router.py)

 6.1 _VALID_QUERY_TYPES:

 _VALID_QUERY_TYPES: frozenset[str] = frozenset({
     # Forward (entity = disease name)
     "symptoms", "medicine", "treatment", "advice",
     "prevention", "department", "profile", "count",
     # Reverse (entity = keyword/constraint, không phải disease)
     "find_by_symptom", "find_by_medicine",
     "find_by_nutrition_avoid", "find_by_nutrition_eat",
     "find_by_prevention",
     # Sentinel
     "unknown",
 })

 _FIND_BY_TYPES: frozenset[str] = frozenset({
     "find_by_symptom", "find_by_medicine",
     "find_by_nutrition_avoid", "find_by_nutrition_eat",
     "find_by_prevention",
 })

 6.2 Prompt full (sẽ paste nguyên bản vào query_router.py):

 You classify a Vietnamese (or English) medical question about the VietMedKG
 knowledge graph and return EXACTLY one JSON object: {"query_type": "...", "entity": "..."}.

 # Knowledge graph fields (VietMedKG)
 - Disease: disease_name, disease_description, disease_category, disease_cause
 - Symptom: disease_symptom (comma-separated blob: "Ho khan, Sốt cao, Đau ngực")
 - Treatment: cure_method, cure_department
 - Medicine: drug_common, drug_recommend (comma-separated blob, mostly
   Vietnamese-prefixed Latin names e.g. "Viên nén Azithromycin, Viên nang Levofloxacin")
 - Advice: nutrition_do_eat, nutrition_not_eat, nutrition_recommend_meal,
   disease_prevention (all comma-separated blobs; nutrition_not_eat samples:
   "Rượu trắng, Bia, Trứng vịt muối, Dưa chua khô"; nutrition_do_eat samples:
   "Trứng, vừng, bắp cải, rau muống, hạt sen")

 # Two query directions
 FORWARD  — user names a disease, asks about its fields. entity = disease name.
 REVERSE  — user names a constraint (symptom / drug / food / prevention method),
            asks WHICH disease matches. entity = the constraint keyword.

 # Valid query_type values (11 total)

 Forward (entity = Vietnamese disease name; null if irrelevant):
   symptoms       → user wants Symptom of disease X
   medicine       → user wants Medicine for disease X
   treatment      → user wants Treatment / cure_method of disease X
   advice         → user wants nutrition advice for disease X
   prevention     → user wants how to prevent disease X
   department     → user wants which medical department treats disease X
   profile        → user wants overview / "what is" disease X
   count          → counting/statistics (entity = null)

 Reverse (entity = constraint keyword, NOT a disease name):
   find_by_symptom        → "which disease has symptom X" (KG: Symptom.disease_symptom)
   find_by_medicine       → "which disease is drug X for"  (KG: Medicine.drug_common/recommend)
   find_by_nutrition_avoid → "which disease should avoid food X" (KG: Advice.nutrition_not_eat)
   find_by_nutrition_eat   → "which disease should eat food X"   (KG: Advice.nutrition_do_eat)
   find_by_prevention      → "X helps prevent which disease"     (KG: Advice.disease_prevention)

 Sentinel:
   unknown → use this when (a) the question mixes multiple unrelated constraints
             (e.g. a long bracketed list of foods + drugs + symptoms), (b) the
             question is about general medical advice without identifiable
             entity, or (c) the intent doesn't match any of the 11 types above.
             Set entity = null. The pipeline will route to semantic search.

 # Rules for "entity"
 - Forward types: Vietnamese disease name only. Strip "bệnh ", "bị ".
   Never include "gì", "nào", "như thế nào" etc.
 - Reverse types: ONE short keyword (1–4 words). If user provides a list of
   multiple keywords (e.g. "[A, B, C, D]"), pick the most specific ONE.
   If picking one would lose key meaning, return query_type="unknown".
 - count and unknown: entity = null.

 # Output
 ONLY a JSON object, no markdown fences, no explanation:
 {"query_type": "...", "entity": "..."}

 # Few-shot examples (mỗi cụm có 1 forward + 1 reverse từ schema thực)

 ## Symptoms
 Q: "tiểu đường có triệu chứng gì"
 A: {"query_type": "symptoms", "entity": "tiểu đường"}

 Q: "bệnh nào có triệu chứng sốt cao"
 A: {"query_type": "find_by_symptom", "entity": "sốt cao"}

 Q: "bệnh nào gây ho khan kéo dài"
 A: {"query_type": "find_by_symptom", "entity": "ho khan"}

 ## Medicine
 Q: "thuốc chữa viêm phổi"
 A: {"query_type": "medicine", "entity": "viêm phổi"}

 Q: "thuốc Azithromycin chữa bệnh nào"
 A: {"query_type": "find_by_medicine", "entity": "Azithromycin"}

 Q: "Levofloxacin dùng cho bệnh gì"
 A: {"query_type": "find_by_medicine", "entity": "Levofloxacin"}

 ## Treatment / Department / Profile
 Q: "cách điều trị viêm khớp như thế nào"
 A: {"query_type": "treatment", "entity": "viêm khớp"}

 Q: "khoa nào điều trị viêm phổi"
 A: {"query_type": "department", "entity": "viêm phổi"}

 Q: "tăng huyết áp là bệnh gì"
 A: {"query_type": "profile", "entity": "tăng huyết áp"}

 ## Advice (nutrition) — forward
 Q: "tiểu đường nên ăn gì"
 A: {"query_type": "advice", "entity": "tiểu đường"}

 Q: "viêm dạ dày kiêng gì"
 A: {"query_type": "advice", "entity": "viêm dạ dày"}

 ## Advice (nutrition) — reverse
 Q: "kiêng rượu bia tốt cho bệnh nào"
 A: {"query_type": "find_by_nutrition_avoid", "entity": "rượu bia"}

 Q: "không nên ăn dưa chua khô là bệnh gì"
 A: {"query_type": "find_by_nutrition_avoid", "entity": "dưa chua khô"}

 Q: "ăn rau muống tốt cho bệnh nào"
 A: {"query_type": "find_by_nutrition_eat", "entity": "rau muống"}

 Q: "hạt sen có tác dụng với bệnh nào"
 A: {"query_type": "find_by_nutrition_eat", "entity": "hạt sen"}

 ## Prevention
 Q: "phòng tránh viêm phổi như thế nào"
 A: {"query_type": "prevention", "entity": "viêm phổi"}

 Q: "rửa tay phòng được bệnh nào"
 A: {"query_type": "find_by_prevention", "entity": "rửa tay"}

 Q: "tiêm vắc-xin BCG phòng bệnh gì"
 A: {"query_type": "find_by_prevention", "entity": "vắc-xin BCG"}

 ## Count
 Q: "bao nhiêu bệnh trong cơ sở dữ liệu"
 A: {"query_type": "count", "entity": null}

 ## Unknown (multi-constraint reverse — câu test của user)
 Q: "Việc tránh ăn [Dưa chua khô, Bia, Rượu trắng, Trứng cút] có thể hỗ trợ điều trị bệnh lý nào?"
 A: {"query_type": "unknown", "entity": null}

 Q: "Tôi nên làm gì khi bị stress công việc"
 A: {"query_type": "unknown", "entity": null}

 ## English
 Q: "symptoms of diabetes"
 A: {"query_type": "symptoms", "entity": "tiểu đường"}

 Q: "which disease has fever as symptom"
 A: {"query_type": "find_by_symptom", "entity": "sốt"}

 (temperature=0.0, max_tokens=160 — đủ cho JSON ngắn, không lan man.)

 Phase 7 — Reverse-query regex patterns (query_router.py)

 Thêm vào classify_cypher_intent, trước cụm profile (để không bị profile catch-all nuốt). Thứ tự: tất cả
 reverse patterns chạy sau forward patterns đã có (forward thường specific hơn). Mỗi cụm dùng _clean_entity
 cho group capture.

 # ── REVERSE: find_by_symptom ─────────────────────────────────────────────
 for pattern in [
     r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:có|gây|biểu hiện bằng|gây ra)\s+(?:triệu chứng|biểu hiện|dấu
 hiệu)\s+(.+?)(?:\?|$)",
     r"(?:triệu chứng|biểu hiện|dấu hiệu)\s+(.+?)\s+(?:là|thuộc)\s+bệnh\s+(?:gì|nào)",
     r"which\s+diseases?\s+(?:has|have)\s+(.+?)\s+(?:as\s+)?symptoms?",
 ]:
     m = re.search(pattern, q, re.IGNORECASE)
     if m:
         return "find_by_symptom", _clean_entity(m.group(1))

 # ── REVERSE: find_by_medicine ────────────────────────────────────────────
 for pattern in [
     r"thuốc\s+(.+?)\s+(?:chữa|điều trị|dùng cho|trị)\s+bệnh\s+(?:gì|nào)",
     r"(.+?)\s+(?:chữa|điều trị|trị)\s+(?:được\s+)?bệnh\s+(?:gì|nào)",
     r"(.+?)\s+dùng cho\s+bệnh\s+(?:gì|nào)",
 ]:
     m = re.search(pattern, q, re.IGNORECASE)
     if m:
         return "find_by_medicine", _clean_entity(m.group(1))

 # ── REVERSE: find_by_nutrition_avoid ─────────────────────────────────────
 for pattern in [
     r"(?:không\s+(?:nên\s+)?ăn|kiêng|tránh\s+ăn)\s+(.+?)\s+(?:tốt\s+cho|là|giúp|chữa|hỗ
 trợ)\s+bệnh\s+(?:gì|nào)",
     r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:nên\s+)?(?:kiêng|tránh|không\s+nên\s+ăn)\s+(.+?)(?:\?|$)",
 ]:
     m = re.search(pattern, q, re.IGNORECASE)
     if m:
         return "find_by_nutrition_avoid", _clean_entity(m.group(1))

 # ── REVERSE: find_by_nutrition_eat ───────────────────────────────────────
 for pattern in [
     r"(?:nên\s+)?ăn\s+(.+?)\s+(?:tốt\s+cho|giúp|có tác dụng (?:với|cho)|hỗ trợ)\s+bệnh\s+(?:gì|nào)",
     r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:nên|cần)\s+ăn\s+(.+?)(?:\?|$)",
 ]:
     m = re.search(pattern, q, re.IGNORECASE)
     if m:
         return "find_by_nutrition_eat", _clean_entity(m.group(1))

 # ── REVERSE: find_by_prevention ──────────────────────────────────────────
 for pattern in [
     r"(.+?)\s+(?:phòng|giúp phòng|ngăn ngừa)\s+(?:được\s+)?bệnh\s+(?:gì|nào)",
     r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:được\s+)?phòng\s+bằng\s+(.+?)(?:\?|$)",
 ]:
     m = re.search(pattern, q, re.IGNORECASE)
     if m:
         return "find_by_prevention", _clean_entity(m.group(1))

 Bracket-list detector ngay trước cả 5 cụm trên — nếu câu chứa […,…,…] ≥ 2 phần tử thì coi như
 multi-constraint → trả (None, None) để LLM gánh (LLM sẽ trả unknown):

 if re.search(r"\[[^\]]+,[^\]]+,[^\]]+", q):
     return None, None

 Phase 8 — Reverse-query Cypher templates (cypher_query_builder.py)

 Thêm theo mẫu find_by_symptom (đã có). Param chung $name (giữ tương thích pipeline), không tier-CASE (entity
  là keyword, không cần ranking).

 _FIND_BY_LIMIT = 10

 _TEMPLATES["find_by_medicine"] = (
     "MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) "
     "WHERE toLower(m.drug_common) CONTAINS toLower($name) "
     "   OR toLower(m.drug_recommend) CONTAINS toLower($name) "
     "RETURN d.disease_name AS disease, "
     "       m.drug_common AS matched_common, "
     "       m.drug_recommend AS matched_recommend "
     f"LIMIT {_FIND_BY_LIMIT}"
 )

 _TEMPLATES["find_by_nutrition_avoid"] = (
     "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
     "WHERE toLower(a.nutrition_not_eat) CONTAINS toLower($name) "
     "RETURN d.disease_name AS disease, "
     "       a.nutrition_not_eat AS matched_advice "
     f"LIMIT {_FIND_BY_LIMIT}"
 )

 _TEMPLATES["find_by_nutrition_eat"] = (
     "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
     "WHERE toLower(a.nutrition_do_eat) CONTAINS toLower($name) "
     "   OR toLower(a.nutrition_recommend_meal) CONTAINS toLower($name) "
     "RETURN d.disease_name AS disease, "
     "       a.nutrition_do_eat AS matched_do_eat, "
     "       a.nutrition_recommend_meal AS matched_recommend "
     f"LIMIT {_FIND_BY_LIMIT}"
 )

 _TEMPLATES["find_by_prevention"] = (
     "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
     "WHERE toLower(a.disease_prevention) CONTAINS toLower($name) "
     "RETURN d.disease_name AS disease, "
     "       a.disease_prevention AS matched_prevention "
     f"LIMIT {_FIND_BY_LIMIT}"
 )

 (Cấu trúc thực tế trong cypher_query_builder.py dùng helper functions, không phải dict — implement sẽ follow
  existing style, công thức trên là semantics.)

 Thêm formatter cho từng type vào format_cypher_result_as_text. Output: bullet list - {disease}:
 {matched_field, cắt 120 ký tự}.

 Phase 9 — Wire reverse trong pipeline (pipeline.py)

 Trong _run_pipeline_inner, sau khi resolve (query_type, entity), trước Step 5 (disambiguation):

 from ai_engine.services.query_router import _FIND_BY_TYPES  # export ra public hoặc duplicate set

 if query_type in _FIND_BY_TYPES:
     if not entity:
         logger.info("Reverse type=%s but no keyword → LightRAG", query_type)
         return await _execute_lightrag_path(question, language, _LIGHTRAG_MODE, start_time)
     logger.info("Route → CYPHER (reverse type=%s keyword='%s' method=%s)",
                 query_type, entity, routing_method)
     return await _execute_cypher_path(
         question=question,
         disease_name=entity,   # tên field tương thích build_cypher_query
         query_type=query_type,
         language=language,
         start_time=start_time,
         exact=False,           # CONTAINS, không equality
     )

 Mở rộng table-layout list (dòng ~345):
 if use_template and query_type in (
     "symptoms", "medicine", "treatment", "count",
     "find_by_symptom", "find_by_medicine",
     "find_by_nutrition_avoid", "find_by_nutrition_eat",
     "find_by_prevention",
 ):
     ...

 Reused Utilities

 - cypher_query_builder.find_by_symptom template (cypher_query_builder.py:369-389) — copy pattern cho 4 type
 mới.
 - _clean_entity (đã sửa ở P1) — dùng cho cả forward và reverse capture group.
 - extract_intent_with_llm (đã viết ở P2) — chỉ thay prompt + valid set.
 - _KEY_LABELS trong text2cypher.py đã có map cho hầu hết alias mới; bổ sung nếu thiếu (matched_common,
 matched_advice, matched_prevention, ...).
 - Dataset gốc: data/processed/preprocessed_data.csv — dùng cho smoke test KG coverage.

 Out of Scope

 - Không thêm find_by_department, find_by_cause, find_by_check_method — gom vào unknown đợt này.
 - Không sửa LightRAG path.
 - Không sửa text2cypher.py SCHEMA_PROMPT (chỉ ảnh hưởng LLM Text2Cypher fallback, không ảnh hưởng intent
 extraction).
 - Không thay đổi mechanism disambiguation cho forward query.

 Verification

 1. LLM prompt sanity (pytest hoặc REPL với 12 câu):
   - Forward: "tiểu đường có triệu chứng gì" → ("symptoms", "tiểu đường")
   - Forward: "thuốc chữa viêm phổi" → ("medicine", "viêm phổi")
   - Forward: "tăng huyết áp là bệnh gì" → ("profile", "tăng huyết áp")
   - Reverse: "bệnh nào có triệu chứng ho khan" → ("find_by_symptom", "ho khan")
   - Reverse: "thuốc Azithromycin chữa bệnh nào" → ("find_by_medicine", "Azithromycin")
   - Reverse: "kiêng rượu bia tốt cho bệnh nào" → ("find_by_nutrition_avoid", "rượu bia")
   - Reverse: "ăn rau muống tốt cho bệnh nào" → ("find_by_nutrition_eat", "rau muống")
   - Reverse: "rửa tay phòng được bệnh nào" → ("find_by_prevention", "rửa tay")
   - Multi-constraint: câu test của user → ("unknown", None)
   - Count: "bao nhiêu bệnh" → ("count", None)
 2. End-to-end qua API:
   - POST /ask {"question": "kiêng dưa chua khô tốt cho bệnh nào"} → query_mode chứa
 cypher:template:find_by_nutrition_avoid, response_type="table", trả về ít nhất 1 disease (theo CSV mẫu đã
 có).
   - POST /ask {"question": "Việc tránh ăn [Dưa chua khô, Bia, Rượu trắng, Trứng cút] có thể hỗ trợ điều trị
 bệnh lý nào?"} → query_mode chứa lightrag, log Pipeline ghi type=unknown method=llm (không còn treatment /
 regex).
   - POST /ask {"question": "tiểu đường có triệu chứng gì"} → vẫn method=regex, CYPHER template — no
 regression forward.
 3. KG coverage smoke (Neo4j Cypher trực tiếp):
 MATCH (a:Advice) WHERE toLower(a.nutrition_not_eat) CONTAINS 'dưa chua khô' RETURN count(*) AS n
 3. n > 0 → template find_by_nutrition_avoid có dữ liệu trả về.
 4. Honest logging:
   - Câu mà regex không match nhưng LLM extract được → log method=llm.
   - Câu mà regex match → log method=regex (LLM không được gọi).
   - Câu mà cả 2 thất bại → log method=llm + đi LightRAG.
 5. No regression forward: chạy lại 9 test case Verification của Phase 1–4 → tất cả vẫn pass với routing như
 trước, chỉ thêm path cho reverse.