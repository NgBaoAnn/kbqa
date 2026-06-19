# Blind Benchmark — AegisHealth KBQA

> **Nguyên tắc thiết kế:**  
> - Không câu nào lấy từ prompt, example, hay pattern regex trong code  
> - Paraphrase thực tế — cách người dùng thực sự gõ  
> - Mỗi câu có **Expected Route** và **Pass Condition** rõ ràng  
> - Thực hiện KHÔNG nhìn vào code trước

---

## Cách chấm điểm

| Trường kiểm tra | Cách xác nhận |
|----------------|---------------|
| `engine` | `metadata.engine` |
| `query_mode` | `metadata.query_mode` |
| `response_type` | `response_type` |
| `has_answer` | `answer` không trống, không phải error message |
| `disclaimer` | `answer` chứa `[!NOTE]` |

**Pass** = tất cả Pass Condition đúng  
**Partial** = route đúng nhưng answer kém  
**Fail** = sai route hoặc crash

---

## Group A: Routing — CYPHER Forward (Paraphrase hoàn toàn mới)

> Không dùng từ nào trong regex pattern hiện tại của `classify_cypher_intent`

| # | Câu hỏi | Expected engine | Expected query_type | Pass Condition |
|---|---------|-----------------|---------------------|----------------|
| B1 | `dấu hiệu nhận biết bệnh sởi là gì?` | `cypher_direct` | `symptoms` | engine=cypher_direct, has_answer |
| B2 | `bệnh lao phổi thường biểu hiện ra sao?` | `cypher_direct` | `symptoms` | engine=cypher_direct, has_answer |
| B3 | `uống thuốc gì để trị viêm họng?` | `cypher_direct` | `medicine` | engine=cypher_direct, has_answer |
| B4 | `viêm dạ dày chữa bằng phương pháp nào?` | `cypher_direct` | `treatment` | engine=cypher_direct, has_answer |
| B5 | `người bệnh gút nên tránh ăn gì?` | `cypher_direct` | `advice` | engine=cypher_direct, has_answer |
| B6 | `làm thế nào để không bị mắc bệnh sốt xuất huyết?` | `cypher_direct` | `prevention` | engine=cypher_direct, has_answer |
| B7 | `đau dây thần kinh tọa nên đến khoa nào để khám?` | `cypher_direct` | `department` | engine=cypher_direct, has_answer |
| B8 | `cho tôi biết tất cả về bệnh hen suyễn` | `cypher_direct` | `profile` | engine=cypher_direct, has_answer |
| B9 | `bệnh tiểu đường kéo theo những bệnh nào khác?` | `cypher_direct` | `linked_diseases` | engine=cypher_direct, has_answer |

---

## Group B: Routing — CYPHER Reverse (Paraphrase từ khóa thực tế)

> Người dùng không biết tên bệnh, chỉ biết triệu chứng/thuốc/thực phẩm

| # | Câu hỏi | Expected engine | Expected query_type | Pass Condition |
|---|---------|-----------------|---------------------|----------------|
| B10 | `tôi bị nhức đầu, chóng mặt, mờ mắt — có thể là bệnh gì?` | `cypher_direct` | `find_by_symptom` | engine=cypher_direct, has_answer |
| B11 | `thuốc Metformin thường được dùng để điều trị bệnh gì?` | `cypher_direct` | `find_by_medicine` | engine=cypher_direct, has_answer |
| B12 | `tránh ăn mỡ động vật thì phòng được bệnh gì?` | `cypher_direct` | `find_by_prevention` | engine=cypher_direct hoặc lightrag, has_answer |
| B13 | `rau cần tây ăn tốt cho bệnh gì?` | `cypher_direct` | `find_by_nutrition_eat` | engine=cypher_direct, has_answer |
| B14 | `bệnh nào không được phép ăn hải sản?` | `cypher_direct` | `find_by_nutrition_avoid` | engine=cypher_direct, has_answer |

---

## Group C: LightRAG — Câu thematic/phân tích thực sự

> Câu hỏi thực tế mà không thể trả lời bằng một template Cypher đơn giản

| # | Câu hỏi | Expected engine | Ghi chú | Pass Condition |
|---|---------|-----------------|---------|----------------|
| B15 | `tại sao phụ nữ sau sinh hay bị thiếu máu?` | `lightrag` | Lý giải nguyên nhân | has_answer, không crash |
| B16 | `stress ảnh hưởng đến hệ tiêu hóa như thế nào?` | `lightrag` | Liên kết tâm lý - thể chất | has_answer |
| B17 | `trẻ em hay mắc những bệnh truyền nhiễm nào nhất?` | `lightrag` | Nhóm dân số, không phải tên bệnh cụ thể | has_answer |
| B18 | `bệnh mãn tính ảnh hưởng đến chất lượng cuộc sống thế nào?` | `lightrag` | Câu hỏi khái niệm rộng | has_answer |
| B19 | `tôi 60 tuổi, huyết áp thường xuyên cao, nên làm gì?` | `lightrag` | Câu hỏi tư vấn cá nhân | has_answer, có disclaimer |
| B20 | `mối liên hệ giữa béo phì và tiểu đường type 2 là gì?` | `lightrag` | So sánh/phân tích | has_answer |

---

## Group D: Adversarial — Câu dễ route nhầm

> Thiết kế để test boundary giữa Cypher và LightRAG

| # | Câu hỏi | Expected route | Giải thích tại sao khó | Pass Condition |
|---|---------|---------------|-------------------------|----------------|
| B21 | `bệnh gout` | `cypher_direct` (profile) | Câu chỉ có tên bệnh, không có verb | engine=cypher_direct, has_answer |
| B22 | `tiểu đường và các biến chứng` | `cypher_direct` (linked_diseases) hoặc `lightrag` | Không rõ intent | has_answer |
| B23 | `thuốc hạ áp` | `lightrag` | Không đủ context — không phải tên bệnh cụ thể | has_answer, không crash |
| B24 | `phòng bệnh` | `lightrag` | Quá mơ hồ | has_answer, không crash |
| B25 | `viêm` | `cypher_direct` (disambiguation) hoặc `lightrag` | Entity quá ngắn, match nhiều | trả lời được, không crash |
| B26 | `bệnh tiểu đường có liên quan đến tim mạch không?` | `cypher_direct` (linked_diseases) | Câu hỏi Yes/No về linked | engine=cypher_direct, has_answer |
| B27 | `cả nhà tôi đều bị cao huyết áp, tôi có bị không?` | `lightrag` | Câu hỏi cá nhân + yếu tố di truyền | has_answer, không crash |
| B28 | `bệnh đái tháo đường type 2 kiêng ăn gì?` | `cypher_direct` (advice) | "đái tháo đường" là alias của "tiểu đường" | engine=cypher_direct, has_answer |

---

## Group E: Input kỳ lạ / Edge cases ngôn ngữ

> Cách gõ thực tế của người Việt: viết tắt, thiếu dấu, lẫn tiếng Anh

| # | Câu hỏi | Expected | Pass Condition |
|---|---------|---------|----------------|
| B29 | `benh tieu duong co trieu chung gi` (không dấu) | `cypher_direct` (symptoms) hoặc `lightrag` | has_answer, không crash |
| B30 | `DM type 2 symptoms` (viết tắt tiếng Anh) | `cypher_direct` hoặc `lightrag` | has_answer |
| B31 | `bp cao uong thuoc gi` (viết tắt + không dấu) | `cypher_direct` (medicine) hoặc `lightrag` | has_answer |
| B32 | `bệnh ... là gì???` (ký tự thừa) | `lightrag` hoặc error graceful | không crash, status rõ ràng |
| B33 | `TIỂU ĐƯỜNG CÓ TRIỆU CHỨNG GÌ` (viết hoa toàn bộ) | `cypher_direct` (symptoms) | engine=cypher_direct, has_answer |
| B34 | `bệnh tim mạch vành là gì ạ?` (thêm "ạ" lịch sự) | `cypher_direct` (profile) hoặc `lightrag` | has_answer |
| B35 | `cho hỏi bệnh thận mạn tính chữa thế nào ạ?` (có "cho hỏi") | `cypher_direct` (treatment) hoặc `lightrag` | has_answer |

---

## Group F: Chất lượng câu trả lời (Answer Quality)

> Route đúng là chưa đủ — answer phải có chất lượng

| # | Câu hỏi | Expected | Quality Criteria |
|---|---------|---------|-----------------|
| B36 | `bệnh viêm loét dạ dày có triệu chứng gì?` | cypher_direct:symptoms | Answer phải đề cập đến ít nhất: đau bụng, ợ chua, buồn nôn |
| B37 | `bệnh tăng huyết áp điều trị bằng thuốc gì?` | cypher_direct:medicine | Answer phải có ít nhất 1 tên thuốc cụ thể |
| B38 | `người bị suy thận nên ăn gì và kiêng gì?` | cypher_direct:advice | Answer phải có cả should_eat và should_avoid |
| B39 | `bệnh gout liên quan đến những bệnh gì?` | cypher_direct:linked_diseases | Phải liệt kê ít nhất 2 bệnh liên quan |
| B40 | `tôi bị sốt cao 40 độ, co giật` | warning | response_type=warning, có ⚠️ và 🏥 CTA |

---

## Group G: Disclaimer logic (câu mới)

> Chỉ kiểm tra `answer` có chứa disclaimer hay không

| # | Câu hỏi | Có disclaimer? | Lý do |
|---|---------|----------------|-------|
| B41 | `bệnh tiểu đường phòng ngừa bằng cách nào?` | ✅ Có | prevention = medical advice |
| B42 | `bao nhiêu loại bệnh có trong hệ thống?` | ❌ Không | count = navigational |
| B43 | `bệnh nào dùng thuốc Amoxicillin?` | ❌ Không | find_by_medicine = reverse lookup |
| B44 | `tôi bị đau đầu mỗi sáng, có thể bị gì?` | ✅ Có | LightRAG medical advice |
| B45 | `khoa nào điều trị bệnh tim mạch?` | ❌ Không | department = navigational |

---

## Scoring Summary Template

```
Nhóm A (9 câu):  ___/9   route đúng
Nhóm B (5 câu):  ___/5   route đúng
Nhóm C (6 câu):  ___/6   has_answer
Nhóm D (8 câu):  ___/8   không crash + has_answer
Nhóm E (7 câu):  ___/7   graceful handling
Nhóm F (5 câu):  ___/5   quality check
Nhóm G (5 câu):  ___/5   disclaimer đúng

TOTAL:           ___/45
```

---

## Quick run script

```bash
#!/bin/bash
BASE="http://localhost:8000/api/v1/query"
PASS=0; FAIL=0

run() {
  local id="$1" question="$2"
  result=$(curl -s -X POST "$BASE" \
    -H "Content-Type: application/json" \
    -d "{\"question\": \"$question\"}")
  engine=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('engine','?'))" 2>/dev/null)
  qmode=$(echo "$result"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('query_mode','?'))" 2>/dev/null)
  rtype=$(echo "$result"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response_type','?'))" 2>/dev/null)
  ans_len=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('answer','')))" 2>/dev/null)
  echo "[$id] engine=$engine | mode=$qmode | type=$rtype | ans_len=$ans_len"
}

run B1  "dấu hiệu nhận biết bệnh sởi là gì?"
run B2  "bệnh lao phổi thường biểu hiện ra sao?"
run B3  "uống thuốc gì để trị viêm họng?"
run B4  "viêm dạ dày chữa bằng phương pháp nào?"
run B5  "người bệnh gút nên tránh ăn gì?"
run B6  "làm thế nào để không bị mắc bệnh sốt xuất huyết?"
run B7  "đau dây thần kinh tọa nên đến khoa nào để khám?"
run B8  "cho tôi biết tất cả về bệnh hen suyễn"
run B9  "bệnh tiểu đường kéo theo những bệnh nào khác?"
run B10 "tôi bị nhức đầu, chóng mặt, mờ mắt — có thể là bệnh gì?"
run B11 "thuốc Metformin thường được dùng để điều trị bệnh gì?"
run B15 "tại sao phụ nữ sau sinh hay bị thiếu máu?"
run B21 "bệnh gout"
run B25 "viêm"
run B28 "bệnh đái tháo đường type 2 kiêng ăn gì?"
run B33 "TIỂU ĐƯỜNG CÓ TRIỆU CHỨNG GÌ"
run B40 "tôi bị sốt cao 40 độ, co giật"
```
