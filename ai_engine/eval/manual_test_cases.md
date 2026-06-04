# Manual Test Cases — AegisHealth KBQA

> Chạy với: `curl -s -X POST http://localhost:8000/api/v1/query -H "Content-Type: application/json" -d '{"question": "..."}'`
> Kiểm tra: `status`, `response_type`, `metadata.engine`, `metadata.query_mode`

---

## Group 1: CYPHER — Template (regex entity extraction)
> Engine: `cypher_direct` | Mode: `cypher:template:*` | Method: `regex`

| # | Câu hỏi | Route mong đợi | response_type |
|---|---------|----------------|---------------|
| T1 | `bệnh tiểu đường có triệu chứng gì?` | `cypher:template:symptoms` | text/table |
| T2 | `bệnh tiểu đường điều trị bằng thuốc gì?` | `cypher:template:medicine` | text/table |
| T3 | `cách điều trị bệnh viêm phổi` | `cypher:template:treatment` | text |
| T4 | `người bị tiểu đường nên ăn gì?` | `cypher:template:advice` | text/table |
| T5 | `phòng tránh bệnh viêm gan B như thế nào?` | `cypher:template:prevention` | text |
| T6 | `bệnh viêm khớp khám ở khoa nào?` | `cypher:template:department` | text |
| T7 | `thông tin tổng hợp về bệnh cao huyết áp` | `cypher:template:profile` | text |
| T8 | `bệnh tiểu đường liên quan đến những bệnh gì?` | `cypher:template:linked_diseases` | text/table |

---

## Group 2: CYPHER — Reverse queries (tìm ngược từ keyword)
> Engine: `cypher_direct` | Mode: `cypher:template:find_by_*` | Method: `llm` (LLM routing)

| # | Câu hỏi | Route mong đợi | Ghi chú |
|---|---------|----------------|---------|
| T9 | `những bệnh nào có triệu chứng sốt cao?` | `cypher:template:find_by_symptom` | keyword="sốt cao" |
| T10 | `bệnh nào dùng thuốc Paracetamol?` | `cypher:template:find_by_medicine` | keyword="Paracetamol" |
| T11 | `những bệnh nào thường gặp ở người cao tuổi?` | `cypher:template:find_by_prevention` | keyword="người cao tuổi" |
| T12 | `bệnh nào nên ăn rau xanh?` | `cypher:template:find_by_nutrition_eat` | keyword="rau xanh" |
| T13 | `bệnh nào cần kiêng đường?` | `cypher:template:find_by_nutrition_avoid` | keyword="đường" |

---

## Group 3: CYPHER — Count / Statistics
> Engine: `cypher_direct` | Mode: `cypher:template:count` | Không cần entity

| # | Câu hỏi | Route mong đợi | response_type |
|---|---------|----------------|---------------|
| T14 | `bao nhiêu bệnh trong hệ thống?` | `cypher:template:count` | text |
| T15 | `cơ sở dữ liệu có bao nhiêu loại thuốc?` | `cypher:template:count` | text |
| T16 | `thống kê số lượng bệnh và triệu chứng` | `cypher:template:count` | text |

---

## Group 4: CYPHER — Disambiguation (nhiều bệnh khớp)
> response_type: text | Mode: `cypher:disambiguation`

| # | Câu hỏi | Mong đợi |
|---|---------|---------|
| T17 | `bệnh viêm có triệu chứng gì?` | Hỏi lại "Tìm thấy N bệnh liên quan..." |
| T18 | `bệnh đường có triệu chứng gì?` | Disambiguation list |

---

## Group 5: CYPHER → LightRAG fallback (entity không có trong KG)
> Engine: `lightrag` | Trigger: entity extracted nhưng 0 match trong Neo4j

| # | Câu hỏi | Mong đợi |
|---|---------|---------|
| T19 | `bệnh abcxyz123 có triệu chứng gì?` | LightRAG fallback (entity not in KG) |
| T20 | `bệnh nhện cắn có điều trị như thế nào?` | LightRAG fallback hoặc cypher nếu có |

---

## Group 6: LightRAG — Semantic / thematic (không có entity cụ thể)
> Engine: `lightrag` | Mode: `mix`

| # | Câu hỏi | Ghi chú |
|---|---------|---------|
| T21 | `các bệnh mãn tính phổ biến nhất ở Việt Nam` | Không có entity → LightRAG |
| T22 | `tại sao người béo phì dễ mắc bệnh tim?` | Câu hỏi lý giải nguyên nhân |
| T23 | `sự khác biệt giữa tiểu đường type 1 và type 2` | So sánh, không regex được |
| T24 | `chế độ ăn lành mạnh cho người bệnh tim mạch` | Semantic, không phải 1 bệnh cụ thể |
| T25 | `bệnh nào có thể phòng ngừa bằng vaccine?` | Thematic query |

---

## Group 7: Mode override (force LightRAG)
> Engine: `lightrag` | Trigger: `mode` field trong request body

| # | Request body | Mong đợi |
|---|-------------|---------|
| T26 | `{"question": "tiểu đường có triệu chứng gì?", "mode": "local"}` | Force LightRAG dù có thể Cypher |
| T27 | `{"question": "viêm phổi điều trị gì?", "mode": "mix"}` | Force mix mode |

---

## Group 8: Warning / Emergency detection
> response_type: `warning` | Chỉ trigger trên QUESTION, không phải answer

| # | Câu hỏi | Mong đợi |
|---|---------|---------|
| T28 | `tôi đang bị đau ngực dữ dội và khó thở` | ⚠️ warning + 🏥 CTA |
| T29 | `tôi uống nhầm thuốc quá liều, giúp tôi với!` | ⚠️ warning |
| T30 | `tôi muốn tự tử` | ⚠️ warning |
| T31 | `bà tôi bị đột quỵ, mặt méo một bên` | ⚠️ warning |
| T32 | `tôi bị chảy máu không cầm được` | ⚠️ warning |

### ⚠️ Negative cases (KHÔNG được trigger warning):
| # | Câu hỏi | Mong đợi |
|---|---------|---------|
| T33 | `triệu chứng của bệnh tim mạch` | text/table (KHÔNG warning) |
| T34 | `bệnh nào gây khó thở?` | text/table (KHÔNG warning) |
| T35 | `đau ngực là triệu chứng của bệnh gì?` | text/table (KHÔNG warning) |

---

## Group 9: Edge cases / Input validation

| # | Câu hỏi / Request | Mong đợi |
|---|------------------|---------|
| T36 | `{"question": ""}` | status: error, INVALID_QUESTION |
| T37 | `{"question": "   "}` | status: error, INVALID_QUESTION |
| T38 | `what diseases cause fever?` (tiếng Anh) | Vẫn trả lời được (LLM routing) |
| T39 | Câu hỏi rất dài (>200 ký tự) | Không crash, xử lý bình thường |

---

## Group 10: Disclaimer logic
> Kiểm tra `answer` có chứa `[!NOTE]` hay không

| # | Câu hỏi | Có disclaimer? |
|---|---------|---------------|
| T40 | `bệnh tiểu đường có triệu chứng gì?` | ✅ Có (symptoms) |
| T41 | `bao nhiêu bệnh trong hệ thống?` | ❌ Không (count) |
| T42 | `bệnh viêm có triệu chứng gì?` (disambiguation) | ❌ Không (disambiguation) |
| T43 | LightRAG semantic query | ✅ Có |
| T44 | Emergency/warning query | ❌ Không (đã có ⚠️ CTA riêng) |

---

## Quick curl script

```bash
#!/bin/bash
BASE="http://localhost:8000/api/v1/query"

test_query() {
  local label="$1"
  local question="$2"
  local mode="$3"

  if [ -z "$mode" ]; then
    payload="{\"question\": \"$question\"}"
  else
    payload="{\"question\": \"$question\", \"mode\": \"$mode\"}"
  fi

  result=$(curl -s -X POST "$BASE" -H "Content-Type: application/json" -d "$payload")
  engine=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('engine','?'))")
  qmode=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('query_mode','?'))")
  rtype=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response_type','?'))")
  status=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))")

  echo "[$label] status=$status | engine=$engine | mode=$qmode | type=$rtype"
}

test_query "T1-symptoms"     "bệnh tiểu đường có triệu chứng gì?"
test_query "T2-medicine"     "bệnh tiểu đường điều trị bằng thuốc gì?"
test_query "T14-count"       "bao nhiêu bệnh trong hệ thống?"
test_query "T21-semantic"    "các bệnh mãn tính phổ biến nhất ở Việt Nam"
test_query "T28-emergency"   "tôi đang bị đau ngực dữ dội và khó thở"
test_query "T33-no-warning"  "triệu chứng của bệnh tim mạch"
test_query "T36-empty"       ""
test_query "T26-mode-force"  "tiểu đường có triệu chứng gì?" "local"
```
