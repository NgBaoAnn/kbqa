# API Reference

Base URL: `http://localhost:8000` · Docs: `/docs` (Swagger) · `/redoc`

Tất cả endpoint trừ `/api/v1/query` và `/health/*` đều yêu cầu **Bearer token** (Supabase JWT).

## Authentication

```
Authorization: Bearer <supabase_access_token>
```

Roles: `user` (default), `reviewer`, `admin`.

---

## Endpoints

### Query (Public - có rate limit)

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/api/v1/query` | Hỏi đáp y tế (standalone, không lưu conversation) |

```json
// Request
{ "question": "Bệnh tiểu đường có triệu chứng gì?", "mode": null }

// Response
{
  "status": "success",
  "response_type": "text",
  "answer": "...",
  "data": [...],
  "metadata": { "engine": "cypher_direct", "execution_time_ms": 120, ... }
}
```

Rate limit: 30 req/min/IP (chỉ endpoint này).

---

### Conversations (Authenticated)

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/api/v1/conversations` | Tạo conversation mới |
| `GET` | `/api/v1/conversations` | Liệt kê conversations của user |
| `GET` | `/api/v1/conversations/{id}` | Chi tiết conversation + messages |
| `POST` | `/api/v1/conversations/{id}/messages` | Gửi tin nhắn (sync) |
| `POST` | `/api/v1/conversations/{id}/messages/stream` | Gửi tin nhắn (SSE streaming) |
| `GET` | `/api/v1/conversations/{id}/export?format=markdown` | Export conversation |

---

### User

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/v1/me` | Thông tin user hiện tại |
| `GET` | `/api/v1/me/preferences` | Lấy user preferences |
| `PATCH` | `/api/v1/me/preferences` | Cập nhật preferences |

Preferences: `language` (vi/en), `explanation_level` (general/detailed/expert), `answer_style` (concise/detailed).

---

### Feedback

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/api/v1/messages/{id}/feedback` | Gửi feedback (up/down + reason) |

---

### Knowledge

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/v1/knowledge/diseases` | Danh sách bệnh (paginated) |
| `GET` | `/api/v1/knowledge/diseases/{name}` | Chi tiết một bệnh |

---

### Admin (admin role required)

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/v1/admin/metrics` | Dashboard metrics |
| `GET` | `/api/v1/admin/review-queue` | Danh sách review items |

---

### Health

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/v1/health` | Health check cơ bản |
| `GET` | `/api/v1/health/deep` | Deep health check (Neo4j, LLM, Supabase) |

---

### Schema

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/v1/schema` | Graph schema info |

---

## Response Types

| `response_type` | Ý nghĩa |
|---|---|
| `text` | Câu trả lời văn bản thuần |
| `table` | Có `data` array cho render bảng |
| `warning` | Cảnh báo y tế |
| `disambiguation` | Nhiều bệnh trùng tên, cần user chọn |

## Error Codes

| Code | HTTP | Ý nghĩa |
|---|---|---|
| `INVALID_QUESTION` | 400 | Câu hỏi rỗng/không hợp lệ |
| `NO_DATA_FOUND` | 404 | Không tìm thấy dữ liệu |
| `CYPHER_GENERATION_FAILED` | 422 | Không thể sinh Cypher query |
| `MODEL_UNAVAILABLE` | 503 | LLM server không khả dụng |
| `TIMEOUT` | 504 | Pipeline timeout (>240s) |
| `RATE_LIMITED` | 429 | Vượt quá rate limit |
