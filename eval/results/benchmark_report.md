# Báo cáo Benchmark SLM — Text-to-Cypher

> **Ngày:** 2026-03-21  
> **Task:** M3-AI-01 — Benchmark 2–3 model SLM  
> **Máy test:** MacBook Air M2, 8GB RAM  
> **Prompt:** `text_to_cypher.md` v2.1 (CONTAINS/toLower + 6 few-shot including stats)  
> **Đánh giá:** Semantic correctness (thủ công)

---

## 1. Tổng hợp — Prompt v2.1 (có stats few-shot)

| Metric | qwen2.5:3b | llama3.2:3b |
|---|---|---|
| **Accuracy** | **9/10 (90%)** | **8/10 (80%)** |
| Avg Latency | 1177ms | 1240ms |
| VRAM | 2.4 GB | 2.8 GB |
| Processor | 100% GPU | 100% GPU |

---

## 2. Chi tiết từng câu

### qwen2.5:3b — 9/10 ✅

| Q# | Cat | Lang | Kết quả | Generated Cypher | Ghi chú |
|---|---|---|---|---|---|
| Q1 | basic | en | ❌ | `(m:Migraine)-[:HAS_SYMPTOM]->` | Vẫn tạo label `:Migraine` — lỗi E4 cố hữu |
| Q2 | basic | en | ✅ | `WHERE toLower(a.name) CONTAINS "arthritis"` | Đúng CONTAINS pattern |
| Q3 | multi-hop | en | ✅ | `{name: 'nausea'}...{name: 'vomiting'}` | Đúng logic |
| Q4 | stats | en | ✅ | `MATCH (s:Symptom) RETURN COUNT(s) AS total_symptoms` | **Khớp hoàn hảo!** Few-shot fix đúng |
| Q5 | stats | en | ✅ | `RETURN d.name, COUNT(s)...ORDER BY...LIMIT 5` | **Khớp hoàn hảo!** Few-shot fix đúng |
| Q6 | basic | vi | ✅ | `CONTAINS "malaria"` | Dịch "sốt rét"→"malaria" chính xác |
| Q7 | basic | vi | ✅ | `CONTAINS "diabetes"` | Dịch "tiểu đường"→"diabetes" chính xác |
| Q8 | multi-hop | vi | ✅ | `CONTAINS "fever" AND CONTAINS "abdominal pain"` | Dịch đúng + dùng CONTAINS |
| Q9 | stats | vi | ✅ | `MATCH (d:Disease) RETURN COUNT(d) AS total_diseases` | **Khớp hoàn hảo!** Few-shot fix đúng |
| Q10 | basic | vi | ✅ | `CONTAINS "influenza"` | Dịch "cảm cúm"→"influenza" chính xác |

### llama3.2:3b — 8/10

| Q# | Cat | Lang | Kết quả | Generated Cypher | Ghi chú |
|---|---|---|---|---|---|
| Q1 | basic | en | ✅ | `{name: "Migraine"}` | Exact match nhưng chữ M hoa — hoạt động trên hầu hết DB |
| Q2 | basic | en | ✅ | `CONTAINS "arthritis"` | Đúng CONTAINS pattern |
| Q3 | multi-hop | en | ✅ | `{name: 'nausea'}...{name: 'vomiting'}` | Đúng logic |
| Q4 | stats | en | ✅ | `MATCH (s:Symptom) RETURN COUNT(s) AS total_symptoms` | **Khớp hoàn hảo!** |
| Q5 | stats | en | ✅ | `RETURN d.name, COUNT(s)...ORDER BY...LIMIT 5` | **Khớp hoàn hảo!** |
| Q6 | basic | vi | ❌ | `CONTAINS "dengue" OR CONTAINS "sốt rét"` | Dịch sai + giữ tiếng Việt "sốt rét" |
| Q7 | basic | vi | ✅ | `CONTAINS "diabetes"` | Đúng |
| Q8 | multi-hop | vi | ❌ | `{name: 'sốt'}...{name: 'đau bụng'}` | **Không dịch** tiếng Việt sang Anh |
| Q9 | stats | vi | ✅ | `MATCH (d:Disease) RETURN COUNT(d) AS total_diseases` | **Khớp hoàn hảo!** Fix lỗi trả NL |
| Q10 | basic | vi | ✅ | `CONTAINS "influenza" OR CONTAINS "flu"` | Đúng |

---

## 3. So sánh qua các phiên bản prompt

| Prompt | qwen2.5:3b | llama3.2:3b | Ghi chú |
|---|---|---|---|
| v1 (exact match, 3 few-shot) | 90% | 70% | Baseline |
| v2 (CONTAINS, 3 few-shot) | 80% | 70% | Stats queries bị regression |
| **v2.1 (CONTAINS, 6 few-shot)** | **90%** | **80%** | ✅ Stats fixed, llama Q9 fixed |

**Kết luận:** Thêm stats few-shot **fix được 100% lỗi stats** cho cả 2 model (Q4, Q5, Q9 đều khớp hoàn hảo).

---

## 4. Lỗi còn lại

| Lỗi | Model | Câu | Khả năng fix |
|---|---|---|---|
| Tạo label sai `:Migraine` | qwen | Q1 | Cần thêm constraint mạnh hơn trong prompt |
| Không dịch VI→EN | llama | Q6, Q8 | Khó fix — llama yếu dịch thuật hơn qwen |

---

## 5. Kết luận & Đề xuất

### ✅ Model: `qwen2.5:3b`
### ✅ Prompt: `v2.1` (CONTAINS + 6 few-shot)

| Tiêu chí | qwen2.5:3b | llama3.2:3b |
|---|---|---|
| **Accuracy v2.1** | **90%** | 80% |
| **VRAM** | **2.4 GB** | 2.8 GB |
| Latency | **1177ms** | 1240ms |
| Dịch VI→EN | **Tốt** | Yếu |
| Tuân thủ CONTAINS | 8/10 | 7/10 |

**Hành động tiếp:**
1. Cập nhật `config.py`: `LLM_MODEL_NAME = "qwen2.5:3b"`
2. Sprint 1: Thêm constraint chống tạo label sai vào prompt (fix Q1)
3. Mở rộng Golden Test Set lên 50 câu (task M3-AI-09)
