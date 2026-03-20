# 09. ĐẠO ĐỨC & AI CÓ TRÁCH NHIỆM — AegisHealth KBQA

> **Ethics & Responsible AI trong Hệ thống Hỏi đáp Y tế**

---

## 1. Tầm quan trọng của Ethics trong AI Y tế

Hệ thống AI cung cấp thông tin y tế mang theo **mức độ rủi ro cao hơn** so với các ứng dụng AI thông thường, vì kết quả đầu ra có thể ảnh hưởng trực tiếp đến quyết định liên quan đến sức khỏe và tính mạng con người. Do đó, việc phân tích đạo đức không phải là bước tùy chọn mà là **yêu cầu bắt buộc** trong thiết kế hệ thống.

---

## 2. Phân tích Các bên Liên quan (Stakeholder Analysis)

### 2.1. Ai hưởng lợi?

| Nhóm | Lợi ích |
|---|---|
| **Người dùng phổ thông** | Tiếp cận thông tin y tế nhanh chóng, miễn phí, bằng ngôn ngữ tự nhiên |
| **Sinh viên y khoa** | Công cụ tra cứu bổ trợ cho việc học tập |
| **Cộng đồng nghiên cứu** | Mô hình tham khảo cho kiến trúc GraphRAG trong healthcare |

### 2.2. Ai có thể bị hại?

| Nhóm | Rủi ro | Biện pháp giảm thiểu |
|---|---|---|
| **Người dùng thiếu kiến thức y khoa** | Hiểu nhầm thông tin hệ thống là chẩn đoán y tế chính thức → tự chữa bệnh sai | Disclaimer bắt buộc trong MỌI câu trả lời; `response_type = "warning"` cho triệu chứng nguy hiểm |
| **Bệnh nhân ở vùng dữ liệu thiếu** | Hệ thống không có thông tin về bệnh đặc thù địa phương → trả kết quả "không tìm thấy" → mất niềm tin | Thông báo rõ ràng phạm vi dữ liệu; kế hoạch mở rộng dataset |
| **Nhóm yếu thế (người già, hiểu biết công nghệ thấp)** | Giao diện chat có thể tạo cảm giác "đang nói chuyện với bác sĩ" | UI design rõ ràng: "Đây là trợ lý thông tin, KHÔNG phải bác sĩ" |

---

## 3. Phân tích Bias (Thiên kiến)

### 3.1. Bias trong Dữ liệu

| Loại Bias | Mô tả | Mức độ ảnh hưởng |
|---|---|---|
| **Geographic Bias** | Dataset Kaggle (Symptom2Disease, Medicine Rec) chủ yếu phản ánh dữ liệu y tế từ Bắc Mỹ và Châu Âu. Các bệnh phổ biến ở Đông Nam Á (sốt xuất huyết, sốt rét, tay chân miệng) có thể thiếu hoặc underrepresented. | 🔴 Cao |
| **Language Bias** | Dữ liệu hoàn toàn bằng tiếng Anh. Khi người dùng Việt Nam hỏi bằng tiếng Việt, LLM phải dịch → rủi ro mất nghĩa hoặc ánh xạ sai entity. | 🟠 Trung bình |
| **Prevalence Bias** | Bệnh phổ biến (cảm cúm, tiểu đường) có nhiều record hơn → hệ thống "biết nhiều hơn" về chúng so với bệnh hiếm. | 🟡 Thấp-Trung bình |
| **Drug Availability Bias** | Thuốc trong dataset có thể không sẵn có ở Việt Nam hoặc có tên thương mại khác. | 🟠 Trung bình |

### 3.2. Bias trong Mô hình

| Loại Bias | Mô tả |
|---|---|
| **Instruction Bias** | SLM có thể ưu tiên sinh Cypher "phổ biến" (lookup đơn giản) hơn truy vấn phức tạp (multi-hop), dẫn đến đơn giản hóa câu hỏi khó. |
| **Anchoring Bias** | Few-shot examples trong prompt có thể khiến model "bám" vào pattern quen thuộc, bỏ qua cách diễn đạt khác của cùng một câu hỏi. |

### 3.3. Chiến lược Giảm thiểu Bias

| Chiến lược | Mô tả | Áp dụng |
|---|---|---|
| **Dataset Audit** | Phân tích phân phối bệnh, triệu chứng, thuốc trong graph. Đánh dấu các vùng thiếu dữ liệu. | Trước deployment |
| **Diverse Few-shot** | Đa dạng hóa ví dụ trong prompt để cover nhiều pattern câu hỏi. | Prompt engineering |
| **Explicit Uncertainty** | Khi kết quả ít hoặc confidence thấp, hệ thống nên nói rõ: "Dữ liệu hệ thống có thể chưa đầy đủ". | Runtime |
| **Regional Data Augmentation** | Bổ sung dữ liệu bệnh phổ biến ở Việt Nam/Đông Nam Á trong các phiên bản sau. | Roadmap |

---

## 4. Tính Giải thích Được (Explainability / XAI)

### 4.1. Lợi thế tự nhiên của GraphRAG

Kiến trúc GraphRAG có lợi thế **vượt trội** về explainability so với Black-box LLM hoặc Vector RAG:

| Khía cạnh | Black-box LLM | Vector RAG | GraphRAG (AegisHealth) |
|---|---|---|---|
| **Nguồn gốc câu trả lời** | Không rõ (embedded trong weights) | Chunks tài liệu (semi-traceable) | Cypher query + Graph nodes/edges (**fully traceable**) |
| **Khả năng audit** | Không thể | Khó (phụ thuộc chunk quality) | Dễ — xem Cypher + kết quả truy vấn |
| **Tái tạo kết quả** | Không đảm bảo | Không đảm bảo | **Deterministic** — cùng Cypher → cùng kết quả |

### 4.2. Traceability Flow

```
Câu hỏi: "Triệu chứng bệnh tiểu đường?"
    ↓
Cypher: MATCH (d:Disease {name:"diabetes"})-[:HAS_SYMPTOM]->(s) RETURN s.name
    ↓ (kiểm chứng được)
Neo4j Result: ["frequent urination", "increased thirst", "fatigue"]
    ↓ (dữ liệu xác định)
Answer: "Bệnh tiểu đường có 3 triệu chứng chính..."
    ↓ (có thể truy ngược hoàn toàn)
```

### 4.3. Metadata Traceability trong API

Mọi response đều kèm trường `metadata.cypher` — cho phép developer, auditor, hoặc chuyên gia y tế truy vết chính xác câu trả lời được sinh ra từ đâu trong Knowledge Graph.

---

## 5. Nguy cơ Lạm dụng (Misuse Risks)

| Rủi ro | Mô tả | Biện pháp |
|---|---|---|
| **Tự chẩn đoán & tự chữa** | Người dùng dựa hoàn toàn vào hệ thống thay vì gặp bác sĩ | Disclaimer y tế bắt buộc; trigger warning cho triệu chứng nguy hiểm; KHÔNG dùng ngôn ngữ chẩn đoán ("Bạn bị bệnh X") |
| **Dữ liệu y tế lỗi thời** | Nếu KG không được cập nhật, thông tin thuốc/phác đồ có thể đã thay đổi | Hiển thị thời điểm cập nhật dữ liệu gần nhất; Continual Learning strategy |
| **Adversarial queries** | Người dùng cố tình nhập câu hỏi nhằm khai thác hệ thống (prompt injection, Cypher injection) | Cypher sanitization (chặn DELETE/DROP); Input validation; Rate limiting |
| **Mạo danh chuyên gia** | Người dùng trích dẫn kết quả hệ thống như "ý kiến bác sĩ" | Watermark rõ ràng: "Thông tin từ AegisHealth KBQA — không phải ý kiến y tế chuyên nghiệp" |

---

## 6. Nguyên tắc Responsible AI áp dụng

| Nguyên tắc | Cách AegisHealth tuân thủ |
|---|---|
| **Transparency** (Minh bạch) | Cypher traceability, metadata trong API, thông báo rõ giới hạn hệ thống |
| **Fairness** (Công bằng) | Dataset audit, bias analysis, kế hoạch bổ sung dữ liệu regional |
| **Safety** (An toàn) | Disclaimer bắt buộc, warning response type, không chẩn đoán |
| **Privacy** (Quyền riêng tư) | Local SLM (không gửi data ra ngoài), không lưu PII, ẩn danh hóa logs |
| **Accountability** (Trách nhiệm) | Hệ thống luôn nêu rõ: "Tham khảo ý kiến bác sĩ", audit trail đầy đủ |
| **Human oversight** (Con người giám sát) | Hệ thống là tool hỗ trợ, KHÔNG thay thế bác sĩ; có kênh phản hồi để chuyên gia kiểm tra |

---

## 7. Checklist Đạo đức trước Deployment

- [ ] Disclaimer y tế xuất hiện trong MỌI câu trả lời (không có ngoại lệ).
- [ ] `response_type = "warning"` trigger đúng cho các triệu chứng nguy hiểm.
- [ ] Hệ thống KHÔNG sử dụng từ ngữ chẩn đoán ("Bạn bị...", "Bạn mắc...").
- [ ] Dataset đã được audit bias (geographic, language, prevalence).
- [ ] Cypher sanitization chặn mọi destructive query.
- [ ] Input validation chặn prompt injection cơ bản.
- [ ] Privacy: không lưu PII từ câu hỏi người dùng.
- [ ] Metadata (Cypher + source nodes) có trong mọi API response.
- [ ] UI hiển thị rõ: "Đây là trợ lý thông tin, KHÔNG phải bác sĩ".
