# CONTEXT.md — Domain Glossary for KBQA (AegisHealth)

> This document defines the **Ubiquitous Language** of the KBQA Medical QA system.
> Every term here has a precise meaning. Code, tests, and documentation
> MUST use these terms consistently.

---

## Core Domain: Medical Question Answering (QA)

| Term | Vietnamese | Definition |
|------|-----------|------------|
| **Question** | Câu hỏi | A natural-language medical query from the user |
| **Intent** | Ý định | The classified purpose of a question (e.g., symptoms, treatment, medicine) |
| **QueryType** | Loại truy vấn | One of: `symptoms`, `treatment`, `medicine`, `advice`, `description`, `general_info`, `prevention`, `associated_disease`, `general` |
| **Entity** | Thực thể | The medical entity extracted from a question (typically a disease name) |
| **QueryResult** | Kết quả truy vấn | The structured output of the QA pipeline: answer + sources + metadata |
| **Pipeline** | Đường ống xử lý | The orchestrator that routes a question through Cypher or LightRAG paths |
| **CypherPath** | Đường Cypher | The structured query path: intent → Cypher → Neo4j → answer synthesis |
| **LightRAGPath** | Đường LightRAG | The semantic retrieval path: question → Qdrant vector search → LLM answer |
| **Fallback** | Dự phòng | When CypherPath returns no results, the system falls back to LightRAGPath |

## Knowledge Graph Domain

| Term | Vietnamese | Definition |
|------|-----------|------------|
| **Disease** | Bệnh | A medical condition node in the VietMedKG graph |
| **Symptom** | Triệu chứng | Signs and symptoms associated with a disease |
| **Treatment** | Phương pháp điều trị | Medical treatments for a disease |
| **Medicine** | Thuốc | Medications prescribed for a disease |
| **Advice** | Lời khuyên | Dietary and preventive advice for a disease |
| **VietMedKG** | — | The Vietnamese Medical Knowledge Graph (ACM TALLIP 2025) |
| **GraphSchema** | Lược đồ đồ thị | The set of node labels and relationship types in Neo4j |

## Relationship Types (Neo4j)

| Relationship | Meaning |
|-------------|---------|
| `HAS_SYMPTOM` | Disease → Symptom |
| `HAS_TREATMENT` | Disease → Treatment |
| `IS_PRESCRIBED` | Disease → Medicine |
| `HAS_ADVICE` | Disease → Advice |
| `IS_LINKED_WITH` | Disease → Disease (comorbidity) |

## Conversation Domain

| Term | Vietnamese | Definition |
|------|-----------|------------|
| **Conversation** | Cuộc hội thoại | A thread of messages between user and assistant |
| **Message** | Tin nhắn | A single turn in a conversation (user or assistant) |
| **Feedback** | Phản hồi | User's rating (up/down) on an assistant message |
| **ReviewItem** | Mục đánh giá | A flagged message queued for admin review |
| **Source** | Nguồn | A provenance/citation record attached to an answer |
| **SafetyLevel** | Mức an toàn | One of: `normal`, `caution`, `emergency` |

## User Domain

| Term | Vietnamese | Definition |
|------|-----------|------------|
| **UserProfile** | Hồ sơ người dùng | Authentication identity from Supabase |
| **UserPreferences** | Tùy chọn | Language, explanation level, answer style settings |
| **Role** | Vai trò | One of: `user`, `reviewer`, `admin` |

## Infrastructure Terms

| Term | Definition |
|------|------------|
| **Port** | An abstract interface defining what the domain needs from infrastructure |
| **Adapter** | A concrete implementation of a Port (e.g., Neo4jGraphAdapter) |
| **UseCase** | An application-layer orchestrator that coordinates domain logic and ports |
| **DI Container** | The FastAPI dependency injection wiring (ports → adapters) |

## Naming Conventions

| Layer | Module naming | Class naming | Example |
|-------|--------------|-------------|---------|
| Domain | `snake_case.py` | `PascalCase` entity/VO | `intent_classifier.py` → `IntentClassification` |
| Port | `snake_case.py` | `IPascalCase` (I-prefix) | `llm.py` → `ILlmProvider` |
| Adapter | `snake_case.py` | `PascalCaseAdapter` | `graph_repository.py` → `Neo4jGraphRepository` |
| UseCase | `snake_case.py` | `PascalCaseUseCase` | `answer_question.py` → `AnswerQuestionUseCase` |
| Router | `snake_case.py` | functions only | `query.py` → `query_endpoint()` |
| Schema | `snake_case.py` | `PascalCase` (Pydantic) | `requests.py` → `MessageCreateRequest` |
