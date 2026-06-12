# Unified Upgrade Plan AegisHealth KBQA - P1 + P2 / 6 Sprint / 12 Tuan

## Summary

- Gop P1 va P2 thanh mot roadmap upgrade san pham: tu he hoi dap that den platform mo rong.
- Thoi luong mac dinh: **6 sprint / 12 tuan**, vi hai plan goc deu 3 sprint / 6 tuan.
- Kien truc giu nguyen: **FastAPI modular service-oriented**, cac service phan mem ngang hang voi `ai_service`, deploy chung app.
- Khong build mobile app trong phase nay; chi thiet ke API de mobile reuse sau.

## Key Architecture Changes

### Backend Services Moi

- `suggestion_service`: sinh 3 follow-up questions.
- `streaming_service`: SSE chat streaming.
- `versioning_service`: prompt/model/KG/pipeline version trace.
- `review_workflow_service`: reviewer workflow.
- `knowledge_admin_service`: KG console, validation, import staging.
- `export_service`: export Markdown/PDF.
- `preference_service`: personalization nhe.
- `experiment_service`: A/B prompt/model.
- `api_key_service`: public API key MVP.
- `ingestion_service`: ingestion jobs.
- `notification_service`: notification events.

### Supabase Schema Mo Rong

- Extend `profiles.role`: `user | reviewer | admin`.
- Extend `review_items`: `assignee_id`, `resolution_type`, `resolution_note`, `resolved_at`, status workflow.
- Them cac bang:
  - `user_preferences`
  - `prompt_versions`
  - `model_versions`
  - `kg_versions`
  - `experiment_variants`
  - `experiment_assignments`
  - `api_keys`
  - `api_key_usage_logs`
  - `ingestion_jobs`
  - `notification_events`

### API Contract Moi

- `POST /api/v1/conversations/{id}/messages/stream`
- `GET /api/v1/messages/{id}/trace`
- `GET /api/v1/conversations/{id}/export?format=markdown|pdf`
- `GET /api/v1/me/preferences`
- `PATCH /api/v1/me/preferences`
- `PATCH /api/v1/admin/review-items/{id}`
- `POST /api/v1/admin/review-items/{id}/assign`
- `POST /api/v1/admin/review-items/{id}/resolve`
- `GET /api/v1/admin/kg/nodes`
- `GET /api/v1/admin/kg/relationships`
- `POST /api/v1/admin/kg/validate`
- `POST /api/v1/admin/kg/import-jobs`
- `GET /api/v1/admin/experiments`
- `POST /api/v1/admin/experiments`
- `PATCH /api/v1/admin/experiments/{id}`
- `POST /api/v1/developer/api-keys`
- `GET /api/v1/developer/api-keys`
- `DELETE /api/v1/developer/api-keys/{id}`
- `GET /api/v1/notifications`

## Sprint Plan

### Sprint 1 - Foundation: RBAC, Versioning, Preferences

**Muc tieu:** dat nen tang quyen truy cap, trace version va personalization nhe cho cac sprint sau.

#### Architect

- Tao migration/RLS cho role `reviewer`, preferences, version tables va review workflow fields.
- Lock OpenAPI examples cho preferences, trace va reviewer APIs.
- Cap nhat service boundaries de cac service moi ngang hang voi `ai_service`.

#### Backend

- Implement `get_reviewer_user` va update permission matrix.
- Implement preferences `GET/PATCH` voi defaults:
  - `language=vi`
  - `explanation_level=general`
  - `answer_style=concise`
- Persist `prompt_version`, `model_name`, `kg_version`, `pipeline_version` vao assistant message va query log.
- Implement `GET /api/v1/messages/{id}/trace`.

#### Frontend

- Build Settings screen cho preferences.
- Message/source panel hien thi prompt/model/KG/pipeline version.
- Role-based navigation cho `user`, `reviewer`, `admin`.

#### Tests

- Backend permission matrix cho user/reviewer/admin.
- Preferences default/update validation.
- Trace endpoint chi cho owner/admin/reviewer hop le truy cap.
- Frontend build pass.

### Sprint 2 - Chat Intelligence: Follow-up + Disambiguation

**Muc tieu:** bien chat thanh hoi dap tu nhien hon, ho tro hoi tiep va entity mo ho bang UI co cau truc.

#### Backend

- Implement `suggestion_service` tra toi da 3 follow-up questions cho answer binh thuong.
- Emergency/safety response khong suggest follow-up nguy hiem.
- Chuan hoa `response_type="disambiguation"` voi `data=[{id,label,description,entity_type,confidence}]`.
- `ai_service` nhan preferences va truyen vao pipeline/prompt context.

#### Frontend

- Suggested question chips fill composer + focus.
- Disambiguation option click tao cau hoi moi dang: `Toi muon hoi ve {label}: {original_question}`.
- Render disambiguation bang structured UI, khong phu thuoc text thuan.

#### Tests

- Follow-up count/content tests.
- Emergency response khong sinh suggested questions.
- Disambiguation contract tests.
- Preferences anh huong metadata/request context.

### Sprint 3 - Streaming + Export/Share

**Muc tieu:** cai thien UX cho LightRAG cham va cho phep nguoi dung luu/xuat hoi thoai.

#### Backend

- Implement SSE streaming bang endpoint `POST /api/v1/conversations/{id}/messages/stream`.
- SSE events bat buoc:
  - `stage`
  - `delta`
  - `sources`
  - `metadata`
  - `final`
  - `error`
- `final` luon la full persisted `ChatResponse`.
- Implement export Markdown/PDF gom messages, sources, safety disclaimer va version trace.

#### Frontend

- Chat dung streaming mac dinh, fallback non-stream neu loi truoc `final`.
- Loading hien thi stage: routing, retrieving, generating, persisting.
- Them export buttons Markdown/PDF trong conversation header.

#### Tests

- SSE event order.
- Final response persisted.
- Export ownership, content, sources, disclaimer.
- Frontend manual QA cho slow LightRAG path.

### Sprint 4 - Human Review Workflow

**Muc tieu:** bien report sai thanh workflow reviewer co assign, resolve va trace du ngu canh.

#### Backend

- Implement assign/resolve/status transition cho `review_items`.
- Status flow: `pending -> in_review -> resolved | dismissed`.
- Resolution types:
  - `kg_fix`
  - `prompt_fix`
  - `no_action`
  - `duplicate`
- Reviewer duoc xu ly queue; admin co toan quyen.

#### Frontend

- Reviewer dashboard rieng hoac tab trong admin area.
- Filter queue theo status/category/assignee.
- Review detail hien thi question, answer, feedback, sources, trace.
- Resolve form co resolution type + note.

#### Tests

- Permission matrix user/reviewer/admin.
- Review transition tests.
- Reviewer khong truy cap admin-only KG/experiment screens.

### Sprint 5 - Admin Knowledge Console + Ingestion Jobs

**Muc tieu:** cung cap console noi bo de inspect KG, chay validation va staging import job.

#### Backend

- Implement KG node/relationship browser.
- Implement validation:
  - duplicate disease
  - missing required properties
  - orphan relationships
  - invalid relationship type
- Implement import staging jobs trong Postgres, khong ghi Neo4j truc tiep neu validation fail.
- DB-backed worker dung `FOR UPDATE SKIP LOCKED`, retry toi da 3 lan.
- Tao notification events khi job `succeeded`/`failed` hoac review assigned.

#### Frontend

- Admin Knowledge Console tabs:
  - Nodes
  - Relationships
  - Validation
  - Import Jobs
- Import job dashboard: create/list/detail/retry/cancel.
- Notification center: unread/read, job/review events.

#### Tests

- KG validation with mocked Neo4j.
- Job lifecycle tests.
- Notification creation/read tests.

### Sprint 6 - API Keys, A/B Testing, Hardening

**Muc tieu:** mo rong platform cho integration ngoai va experiment prompt/model co kiem soat.

#### Backend

- Public API key MVP voi `X-API-Key`.
- Chi luu `key_hash`, raw key tra dung 1 lan khi tao.
- API key scopes:
  - `chat:write`
  - `knowledge:read`
- Experiment variants gom:
  - `experiment_key`
  - `variant_key`
  - `prompt_version`
  - `model_name`
  - `weight`
  - `is_active`
- Deterministic assignment bang hash `user_id + experiment_key`.
- Metrics breakdown theo variant: count, latency, negative feedback rate.

#### Frontend

- Developer/API key screen: create, copy once, list, revoke.
- Admin experiment screen: create/list/disable variant, xem metrics.
- Final polish cho empty/error/loading states.

#### Tests

- API key revoked/scope denied/hash-only storage.
- Deterministic experiment assignment.
- Admin metrics by variant.
- Full regression backend + frontend build.

## Acceptance Criteria

- User hoi dap dai co streaming stage updates va final response luu lich su dung.
- Moi answer binh thuong co toi da 3 follow-up questions.
- Entity mo ho render thanh lua chon co cau truc.
- User export conversation Markdown/PDF co sources, disclaimer, version trace.
- Reviewer nhan, xu ly, resolve report sai.
- Admin xem KG node/relationship, chay validation, tao import staging job.
- Chat trace hien thi prompt/model/KG/pipeline version.
- User preferences anh huong request context.
- Admin chay A/B prompt/model va xem metrics theo variant.
- Public API key goi duoc API theo scope, key bi revoke bi tu choi.

## Assumptions

- Tong phase la **6 sprint / 12 tuan**.
- Khong build mobile app trong phase nay; API duoc thiet ke de mobile dung lai sau.
- Streaming dung **SSE qua fetch POST**, khong dung WebSocket.
- Import batch o phase nay la staging + validation; ghi Neo4j production can explicit admin action.
- DB-backed queue du cho MVP; chua them Redis/Celery.
- Supabase Auth van la auth chinh; backend quan ly app roles, preferences, API keys va reviewer/admin workflow.
