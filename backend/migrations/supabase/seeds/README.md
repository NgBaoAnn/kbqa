# Supabase Manual Test Seeds — AegisHealth KBQA

## Accounts required in Supabase Auth

Trước khi chạy seed, tạo 4 tài khoản trong Supabase Auth
(Authentication → Users → Add user):

| Email | Purpose |
|---|---|
| `manual.user@example.com` | Normal active user — có 2 conversations, messages, sources, feedback, review_item |
| `manual.other@example.com` | User khác — test authorization isolation (không được xem data của manual.user) |
| `manual.admin@example.com` | Admin profile — test admin endpoints (`is_admin()` = true) |
| `manual.inactive@example.com` | Inactive profile — test truy cập bị từ chối (`is_active = false`) |

Dùng bất kỳ mật khẩu nào. Backend dùng Supabase JWT thật để xác thực; seed chỉ tạo app-data rows.

## Chạy seed

**Option A: Supabase SQL Editor**

1. Mở Supabase project → SQL Editor.
2. Paste và chạy `202606110002_manual_test_seed.sql`.
3. Xem RAISE NOTICE output — rows bị SKIP nghĩa là Auth user chưa tồn tại.

**Option B: psql**

```bash
psql "$SUPABASE_DB_URL" \
  -f backend/migrations/supabase/seeds/202606110002_manual_test_seed.sql
```

## Seed là idempotent

Chạy lại không tạo duplicate — mọi insert dùng `ON CONFLICT DO UPDATE`.

## Nội dung seed

### manual.user@example.com

- Profile: role=user, is_active=true
- Conversation 1: "Seed: tư vấn đau đầu" (vi)
  - User message: "Đau đầu kéo dài có nguy hiểm không?"
  - Assistant message (response_type=text, safety=caution, engine=cypher_direct)
  - 2 message_sources: cypher + lightrag_entity
  - query_log: engine=cypher_direct, execution_time_ms=85
  - Feedback: rating=down, reason=incorrect → tạo review_item (status=pending)
- Conversation 2: "Seed: bệnh tiểu đường type 2" (vi)
  - User message + Assistant message (response_type=table, engine=lightrag)
  - query_log: engine=lightrag, execution_time_ms=220

### manual.other@example.com

- Profile: role=user, is_active=true
- Conversation: "Seed: private conversation owned by another user"
  - 2 messages (user + assistant)

### manual.admin@example.com

- Profile: role=admin, is_active=true (no conversations seeded)

### manual.inactive@example.com

- Profile: role=user, is_active=false (no conversations seeded)

## Sign in để lấy token

Sau khi seed xong:

```bash
# Lấy access token cho manual.user
curl -X POST "https://your-project.supabase.co/auth/v1/token?grant_type=password" \
  -H "apikey: YOUR_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email": "manual.user@example.com", "password": "your_password"}'

# Dùng access_token để gọi backend
curl -H "Authorization: Bearer ACCESS_TOKEN" \
  http://localhost:8000/api/v1/me
```
