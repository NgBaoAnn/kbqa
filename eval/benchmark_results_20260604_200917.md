# 📊 Benchmark Report — AegisHealth KBQA
> **Generated**: 2026-06-04 20:32:01  
> **Total cases**: 45

## 📋 Tổng quan

| Nhóm | Mô tả | Câu | ✅ Pass | ❌ Fail |
|------|-------|-----|--------|--------|
| **A** | Forward CYPHER (paraphrase mới) | 9 | 4 | 5 |
| **B** | Reverse CYPHER | 5 | 3 | 2 |
| **C** | LightRAG semantic | 6 | 2 | 4 |
| **D** | Adversarial / boundary | 8 | 3 | 5 |
| **E** | Input kỳ lạ / edge cases | 7 | 6 | 1 |
| **F** | Answer quality | 5 | 2 | 3 |
| **G** | Disclaimer logic | 5 | 3 | 2 |
| | **TỔNG** | **45** | **23** | **22** |

---

## Group A — Forward CYPHER (paraphrase mới)

| ID | Câu hỏi | Engine | Query mode | **Response type** | ms | eng | qtype | rtype | ans | discl | Result |
|----|---------|--------|------------|-------------------|----|-----|-------|-------|-----|-------|--------|
| B1 | dấu hiệu nhận biết bệnh sởi là gì? | `cypher_direct` | `cypher:template:symptoms` | **`table`** | 19846 | ✅ | ✅ | — | ✅ (475c) | — | **✅ PASS** |
| B2 | bệnh lao phổi thường biểu hiện ra sao? | `lightrag` | `cypher:disambiguation` | **`table`** | 6264 | ❌ | ❌ | — | ✅ (194c) | — | **❌ FAIL** |
| B3 | uống thuốc gì để trị viêm họng? | `cypher_direct` | `cypher:template:medicine` | **`table`** | 6598 | ✅ | ✅ | — | ✅ (574c) | — | **✅ PASS** |
| B4 | viêm dạ dày chữa bằng phương pháp nào? | `cypher_direct` | `cypher:template:treatment` | **`table`** | 10634 | ✅ | ✅ | — | ✅ (461c) | — | **✅ PASS** |
| B5 | người bệnh gút nên tránh ăn gì? | `lightrag` | `mix` | **`table`** | 40367 | ❌ | ❌ | — | ✅ (1079c) | — | **❌ FAIL** |
| B6 | làm thế nào để không bị mắc bệnh sốt xuất huyết? | `cypher_direct` | `cypher:template:find_by_prevention` | **`table`** | 31972 | ✅ | ❌ | — | ✅ (3003c) | — | **❌ FAIL** |
| B7 | đau dây thần kinh tọa nên đến khoa nào để khám? | `lightrag` | `mix` | **`text`** | 30038 | ❌ | ❌ | — | ✅ (275c) | — | **❌ FAIL** |
| B8 | cho tôi biết tất cả về bệnh hen suyễn | `lightrag` | `cypher:disambiguation` | **`table`** | 6352 | ❌ | ❌ | — | ✅ (369c) | — | **❌ FAIL** |
| B9 | bệnh tiểu đường kéo theo những bệnh nào khác? | `cypher_direct` | `cypher:template:linked_diseases` | **`table`** | 4817 | ✅ | ✅ | — | ✅ (258c) | — | **✅ PASS** |
## Group B — Reverse CYPHER

| ID | Câu hỏi | Engine | Query mode | **Response type** | ms | eng | qtype | rtype | ans | discl | Result |
|----|---------|--------|------------|-------------------|----|-----|-------|-------|-----|-------|--------|
| B10 | tôi bị nhức đầu, chóng mặt, mờ mắt — có thể là bệnh gì? | `lightrag` | `mix` | **`text`** | 34465 | ❌ | ❌ | — | ✅ (383c) | — | **❌ FAIL** |
| B11 | thuốc Metformin thường được dùng để điều trị bệnh gì? | `cypher_direct` | `cypher:template:find_by_medicine` | **`table`** | 15860 | ✅ | ✅ | — | ✅ (341c) | — | **✅ PASS** |
| B12 | tránh ăn mỡ động vật thì phòng được bệnh gì? | `lightrag` | `mix` | **`text`** | 41801 | — | — | — | ✅ (491c) | — | **✅ PASS** |
| B13 | rau cần tây ăn tốt cho bệnh gì? | `cypher_direct` | `cypher:template:find_by_nutrition_eat` | **`table`** | 17768 | ✅ | ✅ | — | ✅ (309c) | — | **✅ PASS** |
| B14 | bệnh nào không được phép ăn hải sản? | `lightrag` | `mix` | **`text`** | 38116 | ❌ | ❌ | — | ✅ (637c) | — | **❌ FAIL** |
## Group C — LightRAG semantic

| ID | Câu hỏi | Engine | Query mode | **Response type** | ms | eng | qtype | rtype | ans | discl | Result |
|----|---------|--------|------------|-------------------|----|-----|-------|-------|-----|-------|--------|
| B15 | tại sao phụ nữ sau sinh hay bị thiếu máu? | `lightrag` | `mix` | **`text`** | 48988 | ✅ | — | — | ✅ (1189c) | — | **✅ PASS** |
| B16 | stress ảnh hưởng đến hệ tiêu hóa như thế nào? | `cypher_direct` | `cypher:template:advice` | **`text`** | 13338 | ❌ | — | — | ✅ (271c) | — | **❌ FAIL** |
| B17 | trẻ em hay mắc những bệnh truyền nhiễm nào nhất? | `lightrag` | `cypher:disambiguation` | **`table`** | 12279 | ✅ | — | — | ✅ (490c) | — | **✅ PASS** |
| B18 | bệnh mãn tính ảnh hưởng đến chất lượng cuộc sống thế nào? | `cypher_direct` | `cypher:template:advice` | **`table`** | 15020 | ❌ | — | — | ✅ (755c) | — | **❌ FAIL** |
| B19 | tôi 60 tuổi, huyết áp thường xuyên cao, nên làm gì? | `lightrag` | `mix` | **`table`** | 69053 | ✅ | — | — | ✅ (1761c) | ❌ | **❌ FAIL** |
| B20 | mối liên hệ giữa béo phì và tiểu đường type 2 là gì? | `cypher_direct` | `cypher:template:linked_diseases` | **`text`** | 13502 | ❌ | — | — | ✅ (81c) | — | **❌ FAIL** |
## Group D — Adversarial / boundary

| ID | Câu hỏi | Engine | Query mode | **Response type** | ms | eng | qtype | rtype | ans | discl | Result |
|----|---------|--------|------------|-------------------|----|-----|-------|-------|-----|-------|--------|
| B21 | bệnh gout | `lightrag` | `mix` | **`text`** | 53142 | ❌ | ❌ | — | ✅ (1462c) | — | **❌ FAIL** |
| B22 | tiểu đường và các biến chứng | `cypher_direct` | `cypher:template:linked_diseases` | **`table`** | 15597 | — | — | — | ✅ (271c) | — | **✅ PASS** |
| B23 | thuốc hạ áp | `lightrag` | `mix` | **`text`** | 43707 | — | — | — | ✅ (873c) | — | **✅ PASS** |
| B24 | phòng bệnh | 💥ERROR | — | — | 90055 | — | — | — | — | — | **❌ FAIL** |
| B25 | viêm | 💥ERROR | — | — | 90051 | — | — | — | — | — | **❌ FAIL** |
| B26 | bệnh tiểu đường có liên quan đến tim mạch không? | `cypher_direct` | `cypher:template:linked_diseases` | **`text`** | 41726 | ✅ | ✅ | — | ✅ (320c) | — | **✅ PASS** |
| B27 | cả nhà tôi đều bị cao huyết áp, tôi có bị không? | `cypher_direct` | `cypher:template:find_by_prevention` | **`text`** | 14744 | ❌ | — | — | ✅ (176c) | — | **❌ FAIL** |
| B28 | bệnh đái tháo đường type 2 kiêng ăn gì? | `lightrag` | `mix` | **`table`** | 67655 | ❌ | ❌ | — | ✅ (1419c) | — | **❌ FAIL** |
## Group E — Input kỳ lạ / edge cases

| ID | Câu hỏi | Engine | Query mode | **Response type** | ms | eng | qtype | rtype | ans | discl | Result |
|----|---------|--------|------------|-------------------|----|-----|-------|-------|-----|-------|--------|
| B29 | benh tieu duong co trieu chung gi | `cypher_direct` | `cypher:template:symptoms` | **`table`** | 15988 | — | — | — | ✅ (423c) | — | **✅ PASS** |
| B30 | DM type 2 symptoms | `lightrag` | `mix` | **`text`** | 39356 | — | — | — | ✅ (719c) | — | **✅ PASS** |
| B31 | bp cao uong thuoc gi | `lightrag` | `mix` | **`table`** | 47626 | — | — | — | ✅ (821c) | — | **✅ PASS** |
| B32 | bệnh ... là gì??? | `lightrag` | `mix` | **`text`** | 32976 | — | — | — | ✅ (137c) | — | **✅ PASS** |
| B33 | TIỂU ĐƯỜNG CÓ TRIỆU CHỨNG GÌ | `cypher_direct` | `cypher:template:symptoms` | **`table`** | 18278 | ✅ | ✅ | — | ✅ (810c) | — | **✅ PASS** |
| B34 | bệnh tim mạch vành là gì ạ? | `cypher_direct` | `cypher:template:profile` | **`table`** | 38490 | — | ✅ | — | ✅ (1696c) | — | **✅ PASS** |
| B35 | cho hỏi bệnh thận mạn tính chữa thế nào ạ? | `lightrag` | `mix` | **`table`** | 46489 | ❌ | ❌ | — | ✅ (1105c) | — | **❌ FAIL** |
## Group F — Answer quality

| ID | Câu hỏi | Engine | Query mode | **Response type** | ms | eng | qtype | rtype | ans | discl | Result |
|----|---------|--------|------------|-------------------|----|-----|-------|-------|-----|-------|--------|
| B36 | bệnh viêm loét dạ dày có triệu chứng gì? | `lightrag` | `mix` | **`table`** | 50792 | ❌ | ❌ | — | ✅ (1368c) | — | **❌ FAIL** |
| B37 | bệnh tăng huyết áp điều trị bằng thuốc gì? | `lightrag` | `cypher:disambiguation` | **`table`** | 9250 | ❌ | ❌ | — | ✅ (581c) | — | **❌ FAIL** |
| B38 | người bị suy thận nên ăn gì và kiêng gì? | `cypher_direct` | `cypher:template:advice` | **`table`** | 12137 | ✅ | ✅ | — | ✅ (750c) | — | **✅ PASS** |
| B39 | bệnh gout liên quan đến những bệnh gì? | `lightrag` | `cypher:disambiguation` | **`table`** | 8709 | ❌ | ❌ | — | ✅ (159c) | — | **❌ FAIL** |
| B40 | tôi bị sốt cao 40 độ, co giật | `lightrag` | `mix` | **`warning`** | 33155 | — | — | ✅ | ✅ (732c) | — | **✅ PASS** |
## Group G — Disclaimer logic

| ID | Câu hỏi | Engine | Query mode | **Response type** | ms | eng | qtype | rtype | ans | discl | Result |
|----|---------|--------|------------|-------------------|----|-----|-------|-------|-----|-------|--------|
| B41 | bệnh tiểu đường phòng ngừa bằng cách nào? | `cypher_direct` | `cypher:template:find_by_prevention` | **`table`** | 26384 | ✅ | ❌ | — | ✅ (982c) | ❌ | **❌ FAIL** |
| B42 | bao nhiêu loại bệnh có trong hệ thống? | `cypher_direct` | `cypher:template:count` | **`text`** | 10753 | ✅ | ✅ | — | ✅ (50c) | ✅ | **✅ PASS** |
| B43 | bệnh nào dùng thuốc Amoxicillin? | `cypher_direct` | `cypher:template:find_by_medicine` | **`table`** | 15014 | ✅ | ✅ | — | ✅ (223c) | ✅ | **✅ PASS** |
| B44 | tôi bị đau đầu mỗi sáng, có thể bị gì? | `lightrag` | `mix` | **`table`** | 52417 | — | — | — | ✅ (1446c) | ❌ | **❌ FAIL** |
| B45 | khoa nào điều trị bệnh tim mạch? | `cypher_direct` | `cypher:template:department` | **`table`** | 12830 | ✅ | ✅ | — | ✅ (84c) | ✅ | **✅ PASS** |

---

## ❌ Failures (22 câu)

### B2 — bệnh lao phổi thường biểu hiện ra sao?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `cypher:disambiguation`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: —

### B5 — người bệnh gút nên tránh ăn gì?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `mix`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: —

### B6 — làm thế nào để không bị mắc bệnh sốt xuất huyết?
- **Failed checks**: query_type
- **Got engine**: `cypher_direct` (expected: `cypher_direct`)
- **Got query_mode**: `cypher:template:find_by_prevention`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: —

### B7 — đau dây thần kinh tọa nên đến khoa nào để khám?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `mix`
- **Got response_type**: `text` (expected: `any`)
- **Notes**: —

### B8 — cho tôi biết tất cả về bệnh hen suyễn
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `cypher:disambiguation`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: —

### B10 — tôi bị nhức đầu, chóng mặt, mờ mắt — có thể là bệnh gì?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `mix`
- **Got response_type**: `text` (expected: `any`)
- **Notes**: —

### B14 — bệnh nào không được phép ăn hải sản?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `mix`
- **Got response_type**: `text` (expected: `any`)
- **Notes**: —

### B16 — stress ảnh hưởng đến hệ tiêu hóa như thế nào?
- **Failed checks**: engine
- **Got engine**: `cypher_direct` (expected: `lightrag`)
- **Got query_mode**: `cypher:template:advice`
- **Got response_type**: `text` (expected: `any`)
- **Notes**: —

### B18 — bệnh mãn tính ảnh hưởng đến chất lượng cuộc sống thế nào?
- **Failed checks**: engine
- **Got engine**: `cypher_direct` (expected: `lightrag`)
- **Got query_mode**: `cypher:template:advice`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: —

### B19 — tôi 60 tuổi, huyết áp thường xuyên cao, nên làm gì?
- **Failed checks**: disclaimer
- **Got engine**: `lightrag` (expected: `lightrag`)
- **Got query_mode**: `mix`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: câu tư vấn cá nhân → phải có disclaimer

### B20 — mối liên hệ giữa béo phì và tiểu đường type 2 là gì?
- **Failed checks**: engine
- **Got engine**: `cypher_direct` (expected: `lightrag`)
- **Got query_mode**: `cypher:template:linked_diseases`
- **Got response_type**: `text` (expected: `any`)
- **Notes**: —

### B21 — bệnh gout
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `mix`
- **Got response_type**: `text` (expected: `any`)
- **Notes**: entity ngắn, không có verb

### B24 — phòng bệnh
- **Failed checks**: no_crash
- **Error**: timed out

### B25 — viêm
- **Failed checks**: no_crash
- **Error**: timed out

### B27 — cả nhà tôi đều bị cao huyết áp, tôi có bị không?
- **Failed checks**: engine
- **Got engine**: `cypher_direct` (expected: `lightrag`)
- **Got query_mode**: `cypher:template:find_by_prevention`
- **Got response_type**: `text` (expected: `any`)
- **Notes**: câu hỏi di truyền cá nhân

### B28 — bệnh đái tháo đường type 2 kiêng ăn gì?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `mix`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: alias 'đái tháo đường' của 'tiểu đường'

### B35 — cho hỏi bệnh thận mạn tính chữa thế nào ạ?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `mix`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: có 'cho hỏi' + 'ạ'

### B36 — bệnh viêm loét dạ dày có triệu chứng gì?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `mix`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: answer phải có: đau bụng / ợ chua / buồn nôn

### B37 — bệnh tăng huyết áp điều trị bằng thuốc gì?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `cypher:disambiguation`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: answer phải có ít nhất 1 tên thuốc cụ thể

### B39 — bệnh gout liên quan đến những bệnh gì?
- **Failed checks**: engine, query_type
- **Got engine**: `lightrag` (expected: `cypher_direct`)
- **Got query_mode**: `cypher:disambiguation`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: phải liệt kê ít nhất 2 bệnh liên quan

### B41 — bệnh tiểu đường phòng ngừa bằng cách nào?
- **Failed checks**: query_type, disclaimer
- **Got engine**: `cypher_direct` (expected: `cypher_direct`)
- **Got query_mode**: `cypher:template:find_by_prevention`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: prevention = cần disclaimer

### B44 — tôi bị đau đầu mỗi sáng, có thể bị gì?
- **Failed checks**: disclaimer
- **Got engine**: `lightrag` (expected: `any`)
- **Got query_mode**: `mix`
- **Got response_type**: `table` (expected: `any`)
- **Notes**: LightRAG medical advice → cần disclaimer

---

## 📝 Raw Answers (đầy đủ)

### B1 ✅ — dấu hiệu nhận biết bệnh sởi là gì?

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `symptoms` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:symptoms` |
| **response_type** | **`table`** |
| elapsed | 19846ms |
| answer length | 475 chars |

**Answer:**

```
Để nhận biết bệnh sởi, dấu hiệu quan trọng bao gồm:

- Mụn đốm vàng
- Sắc tố niêm mạc miệng
- Nhợt nhạt
- Chảy nước mũi
- Bồn chồn
- Sốt với phát ban
- Sốt thấp
- Tắc nghẽn kết mạc
- Co giật

Đây là những triệu chứng chính mà bệnh sởi thường gây ra. Nếu nghi ngờ mắc bệnh sởi, cần đến bác sĩ để được chẩn đoán chính xác và điều trị kịp thời. 💊

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B2 ❌ — bệnh lao phổi thường biểu hiện ra sao?

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `symptoms` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `lightrag` |
| **query_mode** | `cypher:disambiguation` |
| **response_type** | **`table`** |
| elapsed | 6264ms |
| answer length | 194 chars |

**Answer:**

```
Tìm thấy 4 bệnh liên quan đến "lao phổi". Bạn muốn hỏi về bệnh nào?

  1. Khối u lao phổi
  2. Lao phổi nguyên phát ở trẻ em
  3. Lao phổi phân tán máu cấp tính ở trẻ em
  4. Lao phổi ở tuổi già
```

### B3 ✅ — uống thuốc gì để trị viêm họng?

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `medicine` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:medicine` |
| **response_type** | **`table`** |
| elapsed | 6598ms |
| answer length | 574 chars |

**Answer:**

```
Để trị viêm họng, bạn có thể sử dụng các loại thuốc sau:

- Vitamin C Silvericum Tablet
- Cold Cleaning Capsule
- Ampicillin Capsule
- Ceftadine Capsule
- Amoxicillin Granule
- Cefclor Granule
- Levofloxacin Hydrochloride Capsule
- Cefclor Capsule
- Taurine Detox Viên nén
- Dexamethasone Chậm phát hành Viên nén

Đây là những lựa chọn phổ biến và hiệu quả. Tuy nhiên, trước khi sử dụng, hãy tham khảo ý kiến bác sĩ hoặc dược sĩ chuyên môn. 🌿

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B4 ✅ — viêm dạ dày chữa bằng phương pháp nào?

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `treatment` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:treatment` |
| **response_type** | **`table`** |
| elapsed | 10634ms |
| answer length | 461 chars |

**Answer:**

```
Viêm dạ dày thường được điều trị bằng các phương pháp sau:  
- Điều trị bằng thuốc,  
- Chẳng hạn như thuốc kháng axit,  
- Chất bảo vệ niêm mạc,  
- Thuốc tiêu hóa,  
- Thuốc trung gian và các chế phẩm đơn giản,  
- Cũng như điều trị diệt trừ bệnh nhân nhiễm Hp.  

Điều trị này có tỉ lệ khỏi bệnh là 80%.  
Chúc bạn sức khỏe! 🌿

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B5 ❌ — người bệnh gút nên tránh ăn gì?

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `advice` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`table`** |
| elapsed | 40367ms |
| answer length | 1079 chars |

**Answer:**

```
Người bệnh gút cần tránh một số loại thực phẩm và đồ uống vì chúng có thể làm tăng lượng axit uric trong cơ thể, dẫn đến các triệu chứng của bệnh gút như đau khớp và sưng. Dưới đây là một số gợi ý về thực phẩm và đồ uống mà người bệnh gút nên tránh:

- Rượu bia: Rượu bia có thể làm tăng lượng axit uric trong máu.

- Các loại đồ uống chứa cafein: Như cafe, trà, và một số loại nước ngọt có gas.

- Thực phẩm giàu purin: Purin là một chất có thể chuyển hóa thành axit uric. Các thực phẩm giàu purin bao gồm: các loại đậu (như đậu đũa, đậu gà), các loại hạt (như hạt hướng dương, hạt óc chó), các loại cá (như cá thu, cá ngừ), các loại thịt đỏ (như thịt bò, thịt gà nướng), và các loại trái cây có múi (như dâu tây, dưa hấu).

- Các loại thực phẩm giàu muối: Do người bệnh gút thường bị phù, nên cần hạn chế ăn các loại thực phẩm giàu muối như thịt đỏ, cá, và các loại đậu.

- Các loại thực phẩm giàu dầu và chất béo: Như các loại cá hộp, mayonnaise, và các loại đồ ăn nhanh.

Người bệnh gút nên tham …[truncated]
```

### B6 ❌ — làm thế nào để không bị mắc bệnh sốt xuất huyết?

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `prevention` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:find_by_prevention` |
| **response_type** | **`table`** |
| elapsed | 31972ms |
| answer length | 3003 chars |

**Answer:**

```
Để không bị mắc bệnh sốt xuất huyết, bạn cần thực hiện các biện pháp phòng ngừa như sau:

- Xử lý các khu vực sinh sản và tiêu diệt ấu trùng muỗi:
  - Khai thông mương và cống rãnh, ngăn chặn nước đọng, lấp đầy vùng trũng, lật chảo và chảo để loại bỏ nước đọng.
  - Đối với bình hoa và các thùng chứa khác, hãy cố gắng tránh sử dụng nước sạch để trồng cây.
  
- Thực hiện vệ sinh cá nhân, tránh tiếp xúc với bọ ve và chuột.

- Thực hiện các biện pháp khử trùng chuột và bọ ve bên ngoài gia súc để giảm mật độ bọ ve.

- Nhân viên khi đi vào sa mạc, đồng cỏ hoặc khu vực rừng nên thực hiện các biện pháp bảo vệ cá nhân để ngăn chặn bọ ve cắn.

- Thực hiện các xét nghiệm trong phòng thí nghiệm để xác định sớm bệnh.

- Thực hiện các biện pháp toàn diện để ngăn ngừa sốt xuất huyết do virus, bao gồm khử trùng chuột thường xuyên và khử trùng bọ ve bên ngoài gia súc.

- Thực hiện các biện pháp bảo vệ cá nhân khi tiếp xúc với môi trường có nguy cơ bọ ve cắn.

- Thực hiện các biện pháp dự báo và giám sá…[truncated]
```

### B7 ❌ — đau dây thần kinh tọa nên đến khoa nào để khám?

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `department` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 30038ms |
| answer length | 275 chars |

**Answer:**

```
Đau dây thần kinh tọa nên đến khoa Thần kinh để khám. Đây là khoa chuyên trách trong việc chẩn đoán và điều trị các vấn đề liên quan đến dây thần kinh. Bạn nên liên hệ với bệnh viện để xác nhận thông tin cụ thể, vì không gian và quy trình có thể khác nhau giữa các bệnh viện.
```

### B8 ❌ — cho tôi biết tất cả về bệnh hen suyễn

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `profile` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `lightrag` |
| **query_mode** | `cypher:disambiguation` |
| **response_type** | **`table`** |
| elapsed | 6352ms |
| answer length | 369 chars |

**Answer:**

```
Tìm thấy 28 bệnh liên quan đến "hen suyễn". Bạn muốn hỏi về bệnh nào?

  1. Dược phẩm hen suyễn
  2. Hen suyễn do aspirin
  3. Hen suyễn do tim
  4. Hen suyễn dị ứng
  5. Hen suyễn dị ứng nấm
  6. Hen suyễn dị ứng phấn hoa
  7. Hen suyễn dị ứng thực phẩm
  8. Hen suyễn dị ứng với mạt bụi
  9. Hen suyễn khi mang thai
  10. Hen suyễn kháng hormone
  ... và 18 bệnh khác
```

### B9 ✅ — bệnh tiểu đường kéo theo những bệnh nào khác?

| Field | Value |
|-------|-------|
| Group | A — Forward CYPHER (paraphrase mới) |
| Expected engine | `cypher_direct` |
| Expected query_type | `linked_diseases` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:linked_diseases` |
| **response_type** | **`table`** |
| elapsed | 4817ms |
| answer length | 258 chars |

**Answer:**

```
- Bệnh tiểu đường có thể kéo theo **Nhiễm trùng đường tiết niệu** và **Bệnh thần kinh tiểu đường**.
- Liên quan đến **Bách khoa toàn thư về bệnh, nội khoa, thận** và **Bách khoa toàn thư về bệnh, nội khoa, thần kinh học**.

💡 Mong bệnh nhân giữ sức khỏe tốt.
```

### B10 ❌ — tôi bị nhức đầu, chóng mặt, mờ mắt — có thể là bệnh gì?

| Field | Value |
|-------|-------|
| Group | B — Reverse CYPHER |
| Expected engine | `cypher_direct` |
| Expected query_type | `find_by_symptom` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 34465ms |
| answer length | 383 chars |

**Answer:**

```
Các triệu chứng như nhức đầu, chóng mặt và mờ mắt có thể liên quan đến nhiều tình trạng khác nhau, từ các vấn đề về mắt đơn giản đến các vấn đề sức khỏe nghiêm trọng hơn. Để xác định chính xác nguyên nhân, bạn nên tham khảo ý kiến của một bác sĩ hoặc chuyên gia y tế. Họ có thể yêu cầu bạn thực hiện các xét nghiệm cần thiết để xác định nguyên nhân chính xác của triệu chứng của bạn.
```

### B11 ✅ — thuốc Metformin thường được dùng để điều trị bệnh gì?

| Field | Value |
|-------|-------|
| Group | B — Reverse CYPHER |
| Expected engine | `cypher_direct` |
| Expected query_type | `find_by_medicine` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:find_by_medicine` |
| **response_type** | **`table`** |
| elapsed | 15860ms |
| answer length | 341 chars |

**Answer:**

```
Thuốc Metformin thường được sử dụng để điều trị bệnh **bệnh tiểu đường**. 

- **Liên quan**: 
  - Bệnh tiểu đường
  - Bệnh tiểu đường Gastroparesis

Đây là hai bệnh mà thuốc Metformin được đề cập đến trong dữ liệu. 

Liên quan đến bệnh tiểu đường, Metformin thường được sử dụng để điều trị bệnh tiểu đường loại 2. 

Kết thúc bằng lời chúc: 🌿
```

### B12 ✅ — tránh ăn mỡ động vật thì phòng được bệnh gì?

| Field | Value |
|-------|-------|
| Group | B — Reverse CYPHER |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | acceptable: cypher_direct find_by_prevention OR lightrag |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 41801ms |
| answer length | 491 chars |

**Answer:**

```
Tránh ăn mỡ động vật có thể giúp phòng ngừa một số bệnh liên quan đến việc tích tụ chất béo trong cơ thể, đặc biệt là bệnh gan nhiễm mỡ. Việc này giúp giảm tải cho gan và giảm nguy cơ tổn thương màng tế bào gan, từ đó giảm nguy cơ chuyển sang các bệnh lý nghiêm trọng như xơ gan và ung thư gan.

Ngoài ra, việc tránh ăn mỡ động vật còn có thể giúp giảm nguy cơ mắc các bệnh liên quan đến tiêu hóa, như viêm gan do rượu, viêm gan B và C, và các bệnh về gan khác do vi khuẩn hoặc virus gây ra.
```

### B13 ✅ — rau cần tây ăn tốt cho bệnh gì?

| Field | Value |
|-------|-------|
| Group | B — Reverse CYPHER |
| Expected engine | `cypher_direct` |
| Expected query_type | `find_by_nutrition_eat` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:find_by_nutrition_eat` |
| **response_type** | **`table`** |
| elapsed | 17768ms |
| answer length | 309 chars |

**Answer:**

```
Rau cần tây ăn tốt cho bệnh rối loạn chức năng tiêu hóa. Dưới đây là một số gợi ý món ăn từ rau cần tây cho bệnh này:

- Cháo cần tây và thịt bò
- Súp rau cần tây và dưa chuột
- Cháo khoai môn và cần tây
- Súp nấm và bắp cải
- Bắp cải luộc

Đây đều là những gợi ý từ dữ liệu JSON, phù hợp với nhu cầu của bạn.
```

### B14 ❌ — bệnh nào không được phép ăn hải sản?

| Field | Value |
|-------|-------|
| Group | B — Reverse CYPHER |
| Expected engine | `cypher_direct` |
| Expected query_type | `find_by_nutrition_avoid` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 38116ms |
| answer length | 637 chars |

**Answer:**

```
The text does not specify any particular disease that prohibits eating seafood. It mainly discusses preventive measures and treatments for rabies, which is a disease that can be transmitted through the saliva of infected animals like dogs and wolves. 

If you are asking about a disease that does not allow eating seafood, you might be referring to diseases like Japanese Encephalitis or Malaria, which are transmitted by mosquitoes and are not typically associated with seafood consumption. 

If you need information on a specific disease or condition that prohibits eating seafood, please provide more details or clarify your question.
```

### B15 ✅ — tại sao phụ nữ sau sinh hay bị thiếu máu?

| Field | Value |
|-------|-------|
| Group | C — LightRAG semantic |
| Expected engine | `lightrag` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 48988ms |
| answer length | 1189 chars |

**Answer:**

```
Phụ nữ sau sinh thường gặp vấn đề về thiếu máu do nhiều nguyên nhân khác nhau. Một trong những nguyên nhân chính là lượng máu tăng trong quá trình mang thai và sinh nở, sau khi sinh, cơ thể cần thời gian để hồi phục lượng máu này. Khi mang thai, lượng máu trong cơ thể của phụ nữ có thể tăng khoảng 30-45%. Sau khi sinh, lượng máu này cần mất một thời gian để trở lại mức bình thường.

Ngoài ra, việc mất máu trong quá trình sinh nở cũng là một nguyên nhân gây thiếu máu. Khi sinh nở, lượng máu mất có thể lên đến vài lít, đặc biệt là khi sinh đẻ khó khăn hoặc sinh non.

Thiếu máu sau sinh cũng có thể do thiếu sắt, do cơ thể đã sử dụng nhiều sắt trong quá trình mang thai để nuôi dưỡng thai nhi. Khi thai nhi được sinh ra, lượng sắt này không được tái tạo lại ngay lập tức, dẫn đến tình trạng thiếu sắt.

Ngoài ra, thiếu sắt có thể do chế độ ăn uống không đủ dinh dưỡng, đặc biệt là thiếu sắt, vitamin B12 và vitamin D. 

Để khắc phục tình trạng thiếu máu sau sinh, việc bổ sung dinh dưỡng, đặc biệ…[truncated]
```

### B16 ❌ — stress ảnh hưởng đến hệ tiêu hóa như thế nào?

| Field | Value |
|-------|-------|
| Group | C — LightRAG semantic |
| Expected engine | `lightrag` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:advice` |
| **response_type** | **`text`** |
| elapsed | 13338ms |
| answer length | 271 chars |

**Answer:**

```
Cơ sở dữ liệu chưa có thông tin về ảnh hưởng của stress đến hệ tiêu hóa. Xin vui lòng tham khảo thông tin liên quan đến bệnh tiêu hóa khác.

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B17 ✅ — trẻ em hay mắc những bệnh truyền nhiễm nào nhất?

| Field | Value |
|-------|-------|
| Group | C — LightRAG semantic |
| Expected engine | `lightrag` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `lightrag` |
| **query_mode** | `cypher:disambiguation` |
| **response_type** | **`table`** |
| elapsed | 12279ms |
| answer length | 490 chars |

**Answer:**

```
Tìm thấy 16 bệnh liên quan đến "truyền nhiễm". Bạn muốn hỏi về bệnh nào?

  1. B19 Bệnh thấp khớp truyền nhiễm Microvirus
  2. Ban xuất huyết giảm tiểu cầu truyền nhiễm
  3. Ban đỏ truyền nhiễm
  4. Bệnh bạch cầu truyền nhiễm
  5. Bệnh bạch cầu đơn nhân truyền nhiễm
  6. Bệnh bạch cầu đơn nhân truyền nhiễm ở trẻ em
  7. Bệnh mụn mủ truyền nhiễm
  8. Bệnh truyền nhiễm đường ruột
  9. Bệnh truyền nhiễm ở trẻ em các loại virus herpes 6, 7, 8
  10. Mụn cóc truyền nhiễm
  ... và 6 bệnh khác
```

### B18 ❌ — bệnh mãn tính ảnh hưởng đến chất lượng cuộc sống thế nào?

| Field | Value |
|-------|-------|
| Group | C — LightRAG semantic |
| Expected engine | `lightrag` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:advice` |
| **response_type** | **`table`** |
| elapsed | 15020ms |
| answer length | 755 chars |

**Answer:**

```
Bệnh mãn tính ảnh hưởng đến chất lượng cuộc sống như sau: 

- Tác động đến sức khỏe: Bệnh mãn tính gây ra các vấn đề về sức khỏe mãn tính, như rối loạn chức năng cơ thắt pylori, viêm dạ dày mãn tính, suy giảm chức năng miễn dịch, và nhiễm virus mãn tính.
- Tác động đến tinh thần: Bệnh mãn tính cũng có thể dẫn đến suy giảm tinh thần, như trầm cảm hoặc căng thẳng quá mức.
- Tác động đến lối sống: Người bệnh thường phải thay đổi lối sống của mình, như việc cần phải ăn những thực phẩm tốt cho sức khỏe và tránh những thực phẩm không tốt.

Để phòng ngừa bệnh mãn tính, cần duy trì hạnh phúc tinh thần và lối sống lành mạnh.

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B19 ❌ — tôi 60 tuổi, huyết áp thường xuyên cao, nên làm gì?

| Field | Value |
|-------|-------|
| Group | C — LightRAG semantic |
| Expected engine | `lightrag` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | True |
| Notes | câu tư vấn cá nhân → phải có disclaimer |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`table`** |
| elapsed | 69053ms |
| answer length | 1761 chars |

**Answer:**

```
Đối với người 60 tuổi có huyết áp thường xuyên cao, điều quan trọng là cần theo dõi và kiểm soát huyết áp của mình. Dưới đây là một số gợi ý mà bạn có thể áp dụng:

1. Theo dõi huyết áp: Hãy thực hiện việc đo huyết áp thường xuyên tại nhà, theo hướng dẫn của bác sĩ. Điều này giúp bạn và bác sĩ nắm bắt được mức huyết áp của bạn trong các tình huống hàng ngày.

2. Dùng thuốc: Nếu huyết áp của bạn thường xuyên cao, bác sĩ có thể sẽ kê cho bạn thuốc huyết áp. Hãy tuân thủ chỉ định của bác sĩ và không tự ý thay đổi liều lượng hoặc loại thuốc.

3. Chế độ ăn: Hãy tham khảo ý kiến của bác sĩ hoặc chuyên gia dinh dưỡng để xây dựng một chế độ ăn uống lành mạnh. Một số gợi ý bao gồm giảm lượng muối, hạn chế chất béo động vật, và tăng cường thực phẩm giàu chất xơ như hạt hướng dương và đậu.

4. Tập luyện: Tập thể dục đều đặn, đặc biệt là các bài tập aerobic, có thể giúp giảm huyết áp. Hãy hỏi ý kiến bác sĩ về các bài tập phù hợp với bạn.

5. Giảm cân: Nếu bạn đang vượt quá giới hạn cân nặng, giảm …[truncated]
```

### B20 ❌ — mối liên hệ giữa béo phì và tiểu đường type 2 là gì?

| Field | Value |
|-------|-------|
| Group | C — LightRAG semantic |
| Expected engine | `lightrag` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:linked_diseases` |
| **response_type** | **`text`** |
| elapsed | 13502ms |
| answer length | 81 chars |

**Answer:**

```
Cơ sở dữ liệu chưa có thông tin về mối liên hệ giữa béo phì và tiểu đường type 2.
```

### B21 ❌ — bệnh gout

| Field | Value |
|-------|-------|
| Group | D — Adversarial / boundary |
| Expected engine | `cypher_direct` |
| Expected query_type | `profile` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | entity ngắn, không có verb |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 53142ms |
| answer length | 1462 chars |

**Answer:**

```
Bệnh gout là một bệnh lý liên quan đến viêm khớp, đặc biệt là viêm khớp gút. Bệnh này xảy ra khi có quá nhiều urat trong máu, dẫn đến hình thành các tinh thể urat trong các khớp, đặc biệt là khớp ngón chân cái. Các triệu chứng chính của bệnh gout bao gồm đau khớp dữ dội, sưng, đỏ và ngứa ở các khớp bị ảnh hưởng. Bệnh gout cũng có thể gây ra các biến chứng như tăng axit uric máu, viêm khớp, và các biến chứng khác do axit uric tích tụ trong cơ thể.

Để chẩn đoán bệnh gout, các xét nghiệm có thể bao gồm dự án kiểm tra phòng thí nghiệm thấp khớp, đo hồng ban, kháng thể kháng nguyên hạt nhân liên quan đến thấp khớp (RANA), yếu tố thấp khớp (RF), kiểm tra trực quan hoạt dịch, và kiểm tra trực quan hoạt dịch. 

Phương pháp điều trị bệnh gout bao gồm cả điều trị bằng thuốc và điều trị hỗ trợ. Thuốc điều trị có thể bao gồm các loại thuốc như aspirin, diclofenac, naproxen, và colchicine. 

Để ngăn ngừa tái phát của bệnh gout, việc tuân thủ chế độ ăn uống và luyện tập thể dục phù hợp là rất quan …[truncated]
```

### B22 ✅ — tiểu đường và các biến chứng

| Field | Value |
|-------|-------|
| Group | D — Adversarial / boundary |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | acceptable: linked_diseases hoặc lightrag |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:linked_diseases` |
| **response_type** | **`table`** |
| elapsed | 15597ms |
| answer length | 271 chars |

**Answer:**

```
- **Bệnh tiểu đường** liên quan đến các biến chứng như:
  - **Nhiễm trùng đường tiết niệu** (từ **Bệnh liên quan**).
  - **Bệnh thần kinh tiểu đường** (từ **Bệnh liên quan**).
- 🌿 Mong quý bạn hiểu rõ về các biến chứng này để có biện pháp phòng ngừa và điều trị kịp thời.
```

### B23 ✅ — thuốc hạ áp

| Field | Value |
|-------|-------|
| Group | D — Adversarial / boundary |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | không đủ context, không crash là pass |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 43707ms |
| answer length | 873 chars |

**Answer:**

```
Thuốc hạ áp có thể bao gồm các loại thuốc khác nhau như Levocardine Injection, Levocardine Oral Liquid, Midoline Hydrochloride Tablet, Levocardine để tiêm, viên thuốc bổ tim của vua, Levocarnitine Oral Liquid, và các loại thuốc khác. Để xác định loại thuốc nào phù hợp, cần phải được chỉ định bởi một bác sĩ sau khi đánh giá tình trạng sức khỏe và các yếu tố nguy cơ cá nhân. 

Các phương pháp phòng ngừa và cách ăn uống cũng có thể giúp giảm huyết áp, bao gồm việc ăn thực phẩm khuyến nghị như trứng, gà, hạt sen, hạt hướng dương, và tránh ăn thực phẩm không nên ăn như rượu trắng, trứng vịt muối, hạt hướng dương, và đậu xanh. Đồng thời, cần điều chỉnh tư thế, chế độ ăn uống, và tránh sử dụng các loại thuốc có thể ảnh hưởng đến huyết áp.

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B24 ❌ — phòng bệnh

| Field | Value |
|-------|-------|
| Group | D — Adversarial / boundary |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | quá mơ hồ, không crash là pass |
| **Error** | timed out |

### B25 ❌ — viêm

| Field | Value |
|-------|-------|
| Group | D — Adversarial / boundary |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | entity quá ngắn, disambiguation hoặc lightrag đều ok |
| **Error** | timed out |

### B26 ✅ — bệnh tiểu đường có liên quan đến tim mạch không?

| Field | Value |
|-------|-------|
| Group | D — Adversarial / boundary |
| Expected engine | `cypher_direct` |
| Expected query_type | `linked_diseases` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | — |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:linked_diseases` |
| **response_type** | **`text`** |
| elapsed | 41726ms |
| answer length | 320 chars |

**Answer:**

```
**Bệnh tiểu đường** liên quan đến **tim mạch** thông qua các biến chứng như **bệnh thần kinh tiểu đường**. Đây là một phần của **bách khoa toàn thư về bệnh, nội khoa, thần kinh học**. 

---
Để biết thông tin chính xác và toàn diện về liên quan giữa **bệnh tiểu đường** và **tim mạch**, bạn nên tham khảo chuyên gia y tế.
```

### B27 ❌ — cả nhà tôi đều bị cao huyết áp, tôi có bị không?

| Field | Value |
|-------|-------|
| Group | D — Adversarial / boundary |
| Expected engine | `lightrag` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | câu hỏi di truyền cá nhân |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:find_by_prevention` |
| **response_type** | **`text`** |
| elapsed | 14744ms |
| answer length | 176 chars |

**Answer:**

```
Theo dữ liệu JSON cung cấp, tôi không tìm thấy thông tin liên quan đến cao huyết áp. Tôi khuyên bạn nên berkonsult với bác sĩ chuyên khoa để được tư vấn và điều trị phù hợp. 🛡️
```

### B28 ❌ — bệnh đái tháo đường type 2 kiêng ăn gì?

| Field | Value |
|-------|-------|
| Group | D — Adversarial / boundary |
| Expected engine | `cypher_direct` |
| Expected query_type | `advice` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | alias 'đái tháo đường' của 'tiểu đường' |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`table`** |
| elapsed | 67655ms |
| answer length | 1419 chars |

**Answer:**

```
Đái tháo đường Type 2 thường đi kèm với vấn đề về cân nặng, đặc biệt là thừa cân hoặc béo phì. Do đó, việc kiêng khem một số loại thực phẩm có thể giúp kiểm soát bệnh. Dưới đây là một số loại thực phẩm bạn nên hạn chế:

1. Đồ ăn nhanh, thức ăn ngoài hàng: Chúng thường chứa nhiều đường, chất béo và muối.

2. Đồ ăn chứa nhiều đường: Như bánh mì ngọt, bánh quy, nước ngọt có đường, soda...

3. Đồ ăn chứa nhiều chất béo bão hòa và chất béo chuyển hóa: Như các loại thịt đỏ, mỡ động vật, các loại kem, kem...

4. Đồ ăn chứa nhiều muối: Như các loại xúc xích, thịt hun khói, các loại bánh mì, bánh quy...

5. Đồ ăn chứa nhiều đường tinh luyện: Như đường trắng, đường nâu, đường malt...

6. Các loại thực phẩm có hàm lượng đường cao: Như trái cây có đường như chuối, dâu tây, mận, dưa hấu, và các loại hạt như hạt điều, hạt hướng dương...

Thay vào đó, bạn nên ưu tiên các thực phẩm lành mạnh như rau xanh, trái cây tươi, ngũ cốc nguyên hạt, protein từ các nguồn tự nhiên như cá, thịt gà, trứng, đậu, và …[truncated]
```

### B29 ✅ — benh tieu duong co trieu chung gi

| Field | Value |
|-------|-------|
| Group | E — Input kỳ lạ / edge cases |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | không dấu tiếng Việt |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:symptoms` |
| **response_type** | **`table`** |
| elapsed | 15988ms |
| answer length | 423 chars |

**Answer:**

```
Bệnh tiểu đường có các triệu chứng như:

- Tăng lượng đường trong máu
- Đường tiết niệu
- Khí âm lưỡng hư
- Khát nước quá mức
- Uống quá nhiều
- Lượng đường trong máu cao
- Khát nước
- Đi tiểu quá nhiều
- Giảm cân
- Lượng đường trong máu quá cao sau bữa ăn

Đây là thông tin từ dữ liệu JSON.

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B30 ✅ — DM type 2 symptoms

| Field | Value |
|-------|-------|
| Group | E — Input kỳ lạ / edge cases |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | viết tắt tiếng Anh |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 39356ms |
| answer length | 719 chars |

**Answer:**

```
Based on the information provided in the reference text, the symptoms for DM type 2 (likely referring to Disseminated Mycosis or Disseminated Mycoses, a condition involving the spread of fungal infections) are not explicitly mentioned. The text focuses on other conditions such as Disseminated Mycoses, Hemochromatosis, Ichthyosis, and Neuropsychiatric Disorders. 

If you are asking about the symptoms of a specific condition like DM type 2, please provide more details or clarify which condition you are referring to, as the reference text does not contain information about DM type 2.

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B31 ✅ — bp cao uong thuoc gi

| Field | Value |
|-------|-------|
| Group | E — Input kỳ lạ / edge cases |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | viết tắt + không dấu |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`table`** |
| elapsed | 47626ms |
| answer length | 821 chars |

**Answer:**

```
Để điều trị bệnh bão cấp (bp cao), việc đầu tiên là cần tham khảo ý kiến của bác sĩ hoặc chuyên gia y tế. Họ sẽ đưa ra cho bạn một liệu pháp điều trị phù hợp nhất dựa trên tình trạng sức khỏe của bạn. 

Dưới đây là một số phương pháp điều trị phổ biến mà bác sĩ có thể đề xuất:

1. Thuốc: Bác sĩ có thể kê cho bạn các loại thuốc như beta-blockers, calcium channel blockers, angiotensin-converting enzyme (ACE) inhibitors, hoặc diuretics để giúp hạ huyết áp. 

2. Đời sống lành mạnh: Bác sĩ cũng có thể khuyên bạn nên thay đổi chế độ ăn uống, tập luyện, và giảm cân nếu cần. 

3. Điều trị nguyên nhân: Nếu bão cấp do một nguyên nhân cụ thể như bệnh thận, bệnh gan, hoặc bệnh tim, bác sĩ có thể đề xuất điều trị cho nguyên nhân đó.

Vì vậy, tôi khuyên bạn nên tham khảo ý kiến của bác sĩ để được tư vấn và điều trị phù hợp.
```

### B32 ✅ — bệnh ... là gì???

| Field | Value |
|-------|-------|
| Group | E — Input kỳ lạ / edge cases |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | ký tự thừa, không crash là pass |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`text`** |
| elapsed | 32976ms |
| answer length | 137 chars |

**Answer:**

```
Bạn chưa cung cấp cụ thể tên bệnh. Bạn có thể cho tôi biết tên bệnh cụ thể bạn muốn biết thông tin không? Tôi sẽ giúp bạn tìm hiểu về nó.
```

### B33 ✅ — TIỂU ĐƯỜNG CÓ TRIỆU CHỨNG GÌ

| Field | Value |
|-------|-------|
| Group | E — Input kỳ lạ / edge cases |
| Expected engine | `cypher_direct` |
| Expected query_type | `symptoms` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | viết hoa toàn bộ |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:symptoms` |
| **response_type** | **`table`** |
| elapsed | 18278ms |
| answer length | 810 chars |

**Answer:**

```
**Bệnh tiểu đường** có các triệu chứng như:  
- Tăng lượng đường trong máu  
- Đường tiết niệu  
- Khí âm lưỡng hư  
- Khát nước quá mức  
- Uống quá nhiều  
- Lượng đường trong máu cao  
- Khát nước  
- Đi tiểu quá nhiều  
- Giảm cân  
- Lượng đường trong máu quá cao sau bữa ăn  

Để chẩn đoán bệnh tiểu đường, có các phương pháp như:  
- Phương pháp dải glucose  
- Kháng thể kháng insulin  
- Proinsulin  
- Glucose máu  
- Acetylacetate huyết thanh  
- Glucose lúc đói  
- Urê (GLU)  
- Cholesterol lipoprotein mật độ rất thấp (VLDL-c)  
- VLDL-ch  
- Thử nghiệm dung nạp glucose uống  

Người béo phì và những người có tiền sử gia đình mắc bệnh tiểu đường dễ mắc bệnh này.

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B34 ✅ — bệnh tim mạch vành là gì ạ?

| Field | Value |
|-------|-------|
| Group | E — Input kỳ lạ / edge cases |
| Expected engine | `any` |
| Expected query_type | `profile` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | có 'ạ' lịch sự |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:profile` |
| **response_type** | **`table`** |
| elapsed | 38490ms |
| answer length | 1696 chars |

**Answer:**

```
**Bệnh tim mạch vành** là một tình trạng trong đó xơ vữa động mạch vành gây hẹp hoặc chặn các mạch máu dẫn đến tim, gây thiếu máu cục bộ, thiếu oxy hoặc hoại tử cơ tim. Đây được gọi là bệnh động mạch vành (CHD). 

- **Mô tả**: Xơ vữa động mạch vành tạo mảng xơ vữa, dẫn đến hẹp động mạch vành, gây các triệu chứng khác nhau tùy thuộc vào mức độ hẹp và số lượng động mạch vành bị ảnh hưởng.
- **Nguyên nhân**: Các bức tường động mạch vành tạo mảng xơ vữa, gây hẹp động mạch vành.
- **Triệu chứng**: Tắc nghẽn tim mạch, suy tim, khó thở, nhịp tim nhanh, mệt mỏi, rối loạn tâm trương thất trái, loạn nhịp tim, rung nhĩ mãn tính, tim đập nhanh.
- **Phương pháp chẩn đoán**: Hình ảnh chuyển động, ECG, giám sát ECG, chất kích hoạt plasminogen mô, hình ảnh nghỉ ngơi, kiểm tra enzyme, hình ảnh tưới máu cơ tim, màn hình chuyển động tường, ApoAⅠ (ApoA I), hình ảnh chụp lớp cơ quan.
- **Đối tượng dễ mắc**: Đàn ông trên 40 tuổi, phụ nữ sau mãn kinh, lao động trí óc, béo bụng, huyết áp cao, tăng lipid máu, …[truncated]
```

### B35 ❌ — cho hỏi bệnh thận mạn tính chữa thế nào ạ?

| Field | Value |
|-------|-------|
| Group | E — Input kỳ lạ / edge cases |
| Expected engine | `cypher_direct` |
| Expected query_type | `treatment` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | có 'cho hỏi' + 'ạ' |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`table`** |
| elapsed | 46489ms |
| answer length | 1105 chars |

**Answer:**

```
Bệnh thận mạn tính là một tình trạng nghiêm trọng mà cần sự chăm sóc y tế chuyên nghiệp. Tuy nhiên, tôi có thể cung cấp một số thông tin chung về cách điều trị bệnh thận mạn tính:

1. Điều trị dự phòng: Điều này bao gồm việc kiểm soát các yếu tố nguy cơ như huyết áp cao, glucose trong máu cao, và bệnh tiểu đường. Điều này giúp giảm nguy cơ suy thận.

2. Điều trị triệu chứng: Điều này bao gồm việc điều trị các triệu chứng như mất nước, mất điện giải, và thiếu máu. 

3. Điều trị dự phòng suy thận: Điều này bao gồm việc sử dụng thuốc như thuốc lợi tiểu, thuốc hạ huyết áp, và thuốc điều hòa glucose. 

4. Điều trị suy thận: Điều này bao gồm việc sử dụng thuốc và điều trị dự phòng suy thận, cũng như các phương pháp điều trị khác như lọc máu và ghép thận.

Tuy nhiên, các phương pháp điều trị cụ thể sẽ phụ thuộc vào mức độ suy thận của bạn và các yếu tố khác. Điều quan trọng là phải tuân theo chỉ dẫn của bác sĩ và tham gia vào một chương trình chăm sóc y tế tích cực.

> [!NOTE]
> **Lưu ý:** Th…[truncated]
```

### B36 ❌ — bệnh viêm loét dạ dày có triệu chứng gì?

| Field | Value |
|-------|-------|
| Group | F — Answer quality |
| Expected engine | `cypher_direct` |
| Expected query_type | `symptoms` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | answer phải có: đau bụng / ợ chua / buồn nôn |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`table`** |
| elapsed | 50792ms |
| answer length | 1368 chars |

**Answer:**

```
Bệnh viêm loét dạ dày có một số triệu chứng phổ biến, bao gồm:

- Đau bụng: Đau thường xuất hiện ở vùng giữa hoặc dưới bụng, có thể tăng lên khi đói hoặc sau khi ăn.
- Buồn nôn và nôn: Một số người có thể cảm thấy buồn nôn và nôn, đặc biệt sau khi ăn.
- Đau bụng khi đói: Đau bụng có thể xuất hiện khi bụng đang trống rỗng, thường là vào buổi sáng.
- Đầy hơi và khó tiêu: Một số người có thể cảm thấy đầy hơi và khó tiêu sau khi ăn.
- Đau bụng khi ăn: Đau bụng có thể xuất hiện ngay sau khi ăn hoặc trong khoảng thời gian ngắn sau khi ăn.
- Đau bụng ở vị trí cụ thể: Đau có thể xuất hiện ở một vị trí cụ thể, thường là ở phần dưới của dạ dày hoặc trong vùng bụng sau.
- Đầy hơi và khó tiêu: Một số người có thể cảm thấy đầy hơi và khó tiêu sau khi ăn.
- Đau bụng khi thức dậy: Đau bụng có thể xuất hiện khi bệnh nhân thức dậy vào buổi sáng.
- Đau bụng khi đi ngoài: Đau bụng có thể xuất hiện khi bệnh nhân đi ngoài.
- Đau bụng và nôn ra máu: Trong một số trường hợp nghiêm trọng, bệnh nhân có thể nôn…[truncated]
```

### B37 ❌ — bệnh tăng huyết áp điều trị bằng thuốc gì?

| Field | Value |
|-------|-------|
| Group | F — Answer quality |
| Expected engine | `cypher_direct` |
| Expected query_type | `medicine` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | answer phải có ít nhất 1 tên thuốc cụ thể |
| **engine** | `lightrag` |
| **query_mode** | `cypher:disambiguation` |
| **response_type** | **`table`** |
| elapsed | 9250ms |
| answer length | 581 chars |

**Answer:**

```
Tìm thấy 21 bệnh liên quan đến "tăng huyết áp". Bạn muốn hỏi về bệnh nào?

  1. Bệnh thận tiểu động mạch ác tính do tăng huyết áp ác tính nguyên phát ở người cao tuổi
  2. Bệnh võng mạc tăng huyết áp ác tính
  3. Cuộc khủng hoảng tăng huyết áp ở tuổi già
  4. Hôn mê tăng huyết áp không ketosis
  5. Hội chứng tăng huyết áp khi mang thai
  6. Hội chứng tăng huyết áp tĩnh mạch cửa không xơ cứng tự phát
  7. Tăng huyết áp bẩm sinh ở trẻ em
  8. Tăng huyết áp giả
  9. Tăng huyết áp lành tính, xơ cứng động mạch nhỏ, thận.
  10. Tăng huyết áp nhạy cảm với muối
  ... và 11 bệnh khác
```

### B38 ✅ — người bị suy thận nên ăn gì và kiêng gì?

| Field | Value |
|-------|-------|
| Group | F — Answer quality |
| Expected engine | `cypher_direct` |
| Expected query_type | `advice` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | answer phải có cả nên ăn và kiêng |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:advice` |
| **response_type** | **`table`** |
| elapsed | 12137ms |
| answer length | 750 chars |

**Answer:**

```
- **Nên ăn**: Gà, ngỗng, hạt điều, hạnh nhân. 
- **Không nên ăn**: Trứng cút, gan vịt, gan gà, cánh gà. 
- **Thực đơn gợi ý**: Bánh bao, bánh bao bắp cải, bánh bao thịt lợn bắp cải, cháo óc chó sữa tươi, lát óc chó, gạo lúa mạch nấm shiitake, súp đậu phụ lúa mạch, súp gạo lúa mạch. 

Để phòng ngừa suy thận, người bệnh cần thận trọng, tăng cường tự chăm sóc sức khỏe, tập thể dục, tăng cường khả năng kháng bệnh, và kẹp thời điều trị nhiễm trùng đường hô hấp trên. 

--- 
Đây là một số gợi ý giúp người bệnh suy thận có chế độ ăn uống phù hợp. Hãy nhớ tham khảo ý kiến bác sĩ để có chế độ ăn uống chính xác nhất. 🍽️💊🌿

> [!NOTE]
> **Lưu ý:** Thông tin mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác.
```

### B39 ❌ — bệnh gout liên quan đến những bệnh gì?

| Field | Value |
|-------|-------|
| Group | F — Answer quality |
| Expected engine | `cypher_direct` |
| Expected query_type | `linked_diseases` |
| Expected response_type | `any` |
| Expect disclaimer | None |
| Notes | phải liệt kê ít nhất 2 bệnh liên quan |
| **engine** | `lightrag` |
| **query_mode** | `cypher:disambiguation` |
| **response_type** | **`table`** |
| elapsed | 8709ms |
| answer length | 159 chars |

**Answer:**

```
Tìm thấy 4 bệnh liên quan đến "gout". Bạn muốn hỏi về bệnh nào?

  1. Gout và tăng acid uric máu
  2. Gout ở người già
  3. Gouty tophi
  4. Viêm khớp giả gout
```

### B40 ✅ — tôi bị sốt cao 40 độ, co giật

| Field | Value |
|-------|-------|
| Group | F — Answer quality |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `warning` |
| Expect disclaimer | None |
| Notes | emergency → response_type=warning bắt buộc |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`warning`** |
| elapsed | 33155ms |
| answer length | 732 chars |

**Answer:**

```
⚠️ CẢNH BÁO Y TẾ: Tôi hiểu bạn đang gặp khó khăn. Bạn nên gọi ngay cho bác sĩ hoặc nhân viên y tế để họ có thể hướng dẫn bạn cách xử lý tình huống này. Trong khi chờ họ, hãy đảm bảo rằng bạn ở trong một không gian an toàn, tránh các vật sắc nhọn hoặc bất kỳ vật gì có thể gây thương tích. Bạn cũng nên cố gắng duy trì nhiệt độ cơ thể của mình bằng cách giữ cho mình mát mẻ, ví dụ, bằng cách sử dụng khăn lạnh hoặc chườm nước. 

Tuy nhiên, nếu bạn cảm thấy tình trạng của mình trở nên tồi tệ hơn hoặc nếu bạn không thể kiểm soát được co giật, hãy gọi ngay cho sự giúp đỡ y tế.

🏥 Nếu bạn đang gặp triệu chứng nguy hiểm, VUI LÒNG LIÊN HỆ BÁC SĨ HOẶC GỌI CẤP CỨU NGAY LẬP TỨC.

Hệ thống này KHÔNG thay thế chẩn đoán y tế chuyên nghiệp.
```

### B41 ❌ — bệnh tiểu đường phòng ngừa bằng cách nào?

| Field | Value |
|-------|-------|
| Group | G — Disclaimer logic |
| Expected engine | `cypher_direct` |
| Expected query_type | `prevention` |
| Expected response_type | `any` |
| Expect disclaimer | True |
| Notes | prevention = cần disclaimer |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:find_by_prevention` |
| **response_type** | **`table`** |
| elapsed | 26384ms |
| answer length | 982 chars |

**Answer:**

```
Theo dữ liệu JSON cung cấp, tôi chỉ tìm thấy thông tin liên quan đến phòng ngừa một số bệnh cụ thể. Không có thông tin cụ thể về cách phòng ngừa bệnh tiểu đường. 

- **Bệnh BPH lành tính ở người già**: Y học dự phòng quan trọng trong nhiều lĩnh vực y tế, bao gồm tim mạch và tiết niệu. Có các yếu tố nguy cơ như tuổi tác, gen di truyền, và các yếu tố khác.
- **Bệnh Ban đỏ đa dạng**: Cần biện pháp cách ly bảo vệ và sử dụng phòng cách ly cho trẻ em và người có tình trạng này.
- **Bệnh Bàng quang thần kinh**: Cần cải thiện chức năng bàng quang thông qua việc kiểm soát các yếu tố nguy cơ.
- **Bệnh Béo phì ở người già**: Cần biện pháp phòng ngừa toàn dân để ổn định mức độ béo phì và giảm tỷ lệ mắc bệnh béo phì.
- **Bệnh Parkinson mất trí nhớ**: Nguyên nhân gây ra hội chứng Parkinson chưa rõ, nhưng có thể phòng ngừa nếu nguyên nhân là do yếu tố khác.

**Bệnh tiểu đường** không có thông tin phòng ngừa cụ thể trong dữ liệu được cung cấp. 

Cơ sở dữ liệu chưa có thông tin này. 🌿
```

### B42 ✅ — bao nhiêu loại bệnh có trong hệ thống?

| Field | Value |
|-------|-------|
| Group | G — Disclaimer logic |
| Expected engine | `cypher_direct` |
| Expected query_type | `count` |
| Expected response_type | `any` |
| Expect disclaimer | False |
| Notes | count = không disclaimer |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:count` |
| **response_type** | **`text`** |
| elapsed | 10753ms |
| answer length | 50 chars |

**Answer:**

```
Trong hệ thống AegisHealth, có **8202 loại bệnh**.
```

### B43 ✅ — bệnh nào dùng thuốc Amoxicillin?

| Field | Value |
|-------|-------|
| Group | G — Disclaimer logic |
| Expected engine | `cypher_direct` |
| Expected query_type | `find_by_medicine` |
| Expected response_type | `any` |
| Expect disclaimer | False |
| Notes | reverse lookup = không disclaimer |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:find_by_medicine` |
| **response_type** | **`table`** |
| elapsed | 15014ms |
| answer length | 223 chars |

**Answer:**

```
**Thuốc Amoxicillin** được đề xuất cho **Actinomycosis ở ngực**. 

- **Thuốc được đề xuất**: Amoxicillin natri để tiêm, Hydroprednisone tiêm, Làm sạch phổi mười tám vị thuốc.

Đây là thông tin từ dữ liệu JSON được cung cấp.
```

### B44 ❌ — tôi bị đau đầu mỗi sáng, có thể bị gì?

| Field | Value |
|-------|-------|
| Group | G — Disclaimer logic |
| Expected engine | `any` |
| Expected query_type | `any` |
| Expected response_type | `any` |
| Expect disclaimer | True |
| Notes | LightRAG medical advice → cần disclaimer |
| **engine** | `lightrag` |
| **query_mode** | `mix` |
| **response_type** | **`table`** |
| elapsed | 52417ms |
| answer length | 1446 chars |

**Answer:**

```
Đau đầu mỗi sáng có thể do nhiều nguyên nhân khác nhau, từ nguyên nhân tự nhiên đến các vấn đề sức khỏe nghiêm trọng hơn. Một số nguyên nhân phổ biến có thể bao gồm:

1. Thiếu ngủ hoặc mất ngủ: Nếu bạn không ngủ đủ giấc hoặc không ngủ tốt, có thể gây ra đau đầu.
2. Thiếu máu: Đau đầu do thiếu máu là một trong những nguyên nhân phổ biến. Nếu bạn cảm thấy mệt mỏi, có cảm giác nhạt nhoài, lưỡi nhạt, và có thể có triệu chứng khác như đau đầu, chóng mặt, thì có thể bạn đang thiếu máu.
3. Đau đầu do huyết hư: Đây là một loại đau đầu do thiếu máu và phân phối máu không đầy đủ. Các triệu chứng có thể bao gồm đau đầu không rõ nguyên nhân, mệt mỏi, và lưỡi nhạt.
4. Đau đầu do thiếu máu: Đau đầu do thiếu máu có thể do mất máu quá nhiều, ăn uống không đều, tiêu thụ quá nhiều, hoặc do lao động, bệnh nặng, hoặc nhiều mồ hôi, nôn mửa, lợi tiểu, thương dương, khí, âm dịch.
5. Thiếu máu do thiếu sắt: Thiếu sắt là một nguyên nhân phổ biến của đau đầu. Nếu bạn thường xuyên cảm thấy mệt mỏi, mệt mỏi, lưỡi…[truncated]
```

### B45 ✅ — khoa nào điều trị bệnh tim mạch?

| Field | Value |
|-------|-------|
| Group | G — Disclaimer logic |
| Expected engine | `cypher_direct` |
| Expected query_type | `department` |
| Expected response_type | `any` |
| Expect disclaimer | False |
| Notes | department = không disclaimer |
| **engine** | `cypher_direct` |
| **query_mode** | `cypher:template:department` |
| **response_type** | **`table`** |
| elapsed | 12830ms |
| answer length | 84 chars |

**Answer:**

```
- Bệnh tim mạch được điều trị tại Khoa Nội khoa và Khoa Tim mạch. 
---
Hoàn thành! 🌿
```
