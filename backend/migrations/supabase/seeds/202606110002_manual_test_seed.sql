-- AegisHealth KBQA manual test seed — Sprint 3 enhanced.
--
-- Run after:
--   1. backend/migrations/supabase/versions/202606110001_app_core_schema.sql
--   2. Creating the emails below in Supabase Auth (Authentication → Users).
--
-- This file is intentionally idempotent:
--   ON CONFLICT DO UPDATE is used for all inserts so re-running is safe.
--
-- This seed does NOT insert into auth.users or auth.identities.
-- Supabase Auth remains the sole owner of registration and login.
--
-- See backend/migrations/supabase/seeds/README.md for step-by-step instructions.

do $$
declare
  -- Auth user IDs (resolved from auth.users by email)
  normal_user_id uuid;
  other_user_id uuid;
  admin_user_id uuid;
  inactive_user_id uuid;

  -- Stable UUIDs so idempotent re-runs produce the same rows.
  normal_conversation_id     uuid := '11111111-1111-4111-8111-111111111111';
  normal_conversation2_id    uuid := '11111111-1111-4111-8111-111111111112';
  other_conversation_id      uuid := '22222222-2222-4222-8222-222222222222';

  normal_user_message_id     uuid := '33333333-3333-4333-8333-333333333333';
  normal_assistant_message_id uuid := '44444444-4444-4444-8444-444444444444';
  normal_user_msg2_id        uuid := '33333333-3333-4333-8333-333333333334';
  normal_assistant_msg2_id   uuid := '44444444-4444-4444-8444-444444444445';

  other_user_message_id      uuid := '55555555-5555-4555-8555-555555555555';
  other_assistant_message_id uuid := '66666666-6666-4666-8666-666666666666';

  normal_query_log_id        uuid := '77777777-7777-4777-8777-777777777777';
  normal_query_log2_id       uuid := '77777777-7777-4777-8777-777777777778';

  source1_id                 uuid := '88888888-8888-4888-8888-888888888881';
  source2_id                 uuid := '88888888-8888-4888-8888-888888888882';

  feedback_id                uuid := '99999999-9999-4999-8999-999999999999';
  review_item_id             uuid := 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa';

begin
  -- ── Resolve auth user IDs ────────────────────────────────────────────────
  select id into normal_user_id   from auth.users where email = 'manual.user@example.com';
  select id into other_user_id    from auth.users where email = 'manual.other@example.com';
  select id into admin_user_id    from auth.users where email = 'manual.admin@example.com';
  select id into inactive_user_id from auth.users where email = 'manual.inactive@example.com';

  -- ── Normal user ──────────────────────────────────────────────────────────
  if normal_user_id is null then
    raise notice 'SKIP: auth user manual.user@example.com not found. Create it in Supabase Auth first.';
  else
    -- Profile
    insert into public.profiles (id, display_name, role, is_active)
    values (normal_user_id, 'Manual User', 'user', true)
    on conflict (id) do update
    set display_name = excluded.display_name,
        role         = excluded.role,
        is_active    = excluded.is_active;

    -- ── Conversation 1: headache Q&A ─────────────────────────────────────
    insert into public.conversations (id, user_id, title, language)
    values (normal_conversation_id, normal_user_id, 'Seed: tư vấn đau đầu', 'vi')
    on conflict (id) do update
    set title      = excluded.title,
        language   = excluded.language,
        updated_at = timezone('utc', now());

    -- Messages for conversation 1
    insert into public.messages (id, conversation_id, role, content, response_type, data, safety, metadata)
    values
      (
        normal_user_message_id,
        normal_conversation_id,
        'user',
        'Đau đầu kéo dài có nguy hiểm không?',
        null, null, null,
        '{"seed": true, "source": "manual_test"}'::jsonb
      ),
      (
        normal_assistant_message_id,
        normal_conversation_id,
        'assistant',
        'Đau đầu kéo dài có thể do nhiều nguyên nhân: căng thẳng, thiếu ngủ, mất nước, hoặc bệnh lý nghiêm trọng hơn như tăng huyết áp, viêm màng não. Nếu đau đầu dữ dội và đột ngột, kèm nôn ói, yếu liệt tay chân hoặc rối loạn ý thức, người bệnh cần đến cơ sở y tế ngay lập tức.',
        'text',
        null,
        '{"level": "caution", "requires_emergency_notice": false, "disclaimer": "Thông tin chỉ mang tính chất tham khảo. Vui lòng tham khảo ý kiến bác sĩ."}'::jsonb,
        '{"engine": "cypher_direct", "query_mode": "cypher:template:symptoms", "execution_time_ms": 85, "source_count": 2, "seed": true}'::jsonb
      )
    on conflict (id) do update
    set content       = excluded.content,
        response_type = excluded.response_type,
        data          = excluded.data,
        safety        = excluded.safety,
        metadata      = excluded.metadata;

    -- Message sources for assistant message 1
    insert into public.message_sources (id, message_id, source_type, title, snippet, metadata, rank)
    values
      (
        source1_id,
        normal_assistant_message_id,
        'cypher',
        'Neo4j VietMedKG',
        'MATCH (d:Disease {disease_name: "Đau đầu"})-[:HAS_SYMPTOM]->(s:Symptom) RETURN s.name',
        '{"engine": "cypher_direct", "query_mode": "cypher:template:symptoms", "seed": true}'::jsonb,
        1
      ),
      (
        source2_id,
        normal_assistant_message_id,
        'lightrag_entity',
        'Đau đầu (Headache)',
        'Đau đầu là triệu chứng phổ biến liên quan đến nhiều bệnh lý khác nhau.',
        '{"engine": "lightrag", "query_mode": "mix", "seed": true}'::jsonb,
        2
      )
    on conflict (id) do update
    set snippet  = excluded.snippet,
        metadata = excluded.metadata,
        rank     = excluded.rank;

    -- Query log for conversation 1
    insert into public.query_logs (id, message_id, engine, query_mode, execution_time_ms, source_count, status, metadata)
    values (
      normal_query_log_id,
      normal_assistant_message_id,
      'cypher_direct',
      'cypher:template:symptoms',
      85,
      2,
      'success',
      '{"seed": true, "ai_called": true}'::jsonb
    )
    on conflict (id) do update
    set message_id        = excluded.message_id,
        engine            = excluded.engine,
        query_mode        = excluded.query_mode,
        execution_time_ms = excluded.execution_time_ms,
        source_count      = excluded.source_count,
        status            = excluded.status,
        metadata          = excluded.metadata;

    -- Negative feedback + review item (for admin/review queue demo)
    insert into public.feedback (id, message_id, user_id, rating, reason, comment)
    values (
      feedback_id,
      normal_assistant_message_id,
      normal_user_id,
      'down',
      'incorrect',
      'Câu trả lời thiếu thông tin về điều trị.'
    )
    on conflict (id) do update
    set rating  = excluded.rating,
        reason  = excluded.reason,
        comment = excluded.comment;

    insert into public.review_items (id, feedback_id, status, category)
    values (
      review_item_id,
      feedback_id,
      'pending',
      'answer_quality'
    )
    on conflict (id) do update
    set status   = excluded.status,
        category = excluded.category;

    -- ── Conversation 2: diabetes Q&A ──────────────────────────────────────
    insert into public.conversations (id, user_id, title, language)
    values (normal_conversation2_id, normal_user_id, 'Seed: bệnh tiểu đường type 2', 'vi')
    on conflict (id) do update
    set title      = excluded.title,
        language   = excluded.language,
        updated_at = timezone('utc', now());

    insert into public.messages (id, conversation_id, role, content, response_type, data, safety, metadata)
    values
      (
        normal_user_msg2_id,
        normal_conversation2_id,
        'user',
        'Bệnh tiểu đường type 2 có những triệu chứng gì?',
        null, null, null,
        '{"seed": true, "source": "manual_test"}'::jsonb
      ),
      (
        normal_assistant_msg2_id,
        normal_conversation2_id,
        'assistant',
        'Bệnh tiểu đường type 2 thường có các triệu chứng: khát nước nhiều, đi tiểu nhiều lần, mệt mỏi, mờ mắt, vết thương lâu lành. Nhiều trường hợp không có triệu chứng rõ ràng ở giai đoạn đầu.',
        'table',
        '[{"triệu chứng": "Khát nước nhiều"}, {"triệu chứng": "Đi tiểu nhiều"}, {"triệu chứng": "Mệt mỏi"}, {"triệu chứng": "Mờ mắt"}]'::jsonb,
        '{"level": "normal", "requires_emergency_notice": false, "disclaimer": "Thông tin chỉ mang tính chất tham khảo."}'::jsonb,
        '{"engine": "lightrag", "query_mode": "mix", "execution_time_ms": 220, "source_count": 1, "seed": true}'::jsonb
      )
    on conflict (id) do update
    set content       = excluded.content,
        response_type = excluded.response_type,
        data          = excluded.data,
        safety        = excluded.safety,
        metadata      = excluded.metadata;

    insert into public.query_logs (id, message_id, engine, query_mode, execution_time_ms, source_count, status, metadata)
    values (
      normal_query_log2_id,
      normal_assistant_msg2_id,
      'lightrag',
      'mix',
      220,
      1,
      'success',
      '{"seed": true, "ai_called": true}'::jsonb
    )
    on conflict (id) do update
    set message_id        = excluded.message_id,
        engine            = excluded.engine,
        query_mode        = excluded.query_mode,
        execution_time_ms = excluded.execution_time_ms,
        source_count      = excluded.source_count,
        status            = excluded.status,
        metadata          = excluded.metadata;

  end if;  -- end normal_user_id block

  -- ── Other user (authorization isolation) ────────────────────────────────
  if other_user_id is null then
    raise notice 'SKIP: auth user manual.other@example.com not found. Create it in Supabase Auth first.';
  else
    insert into public.profiles (id, display_name, role, is_active)
    values (other_user_id, 'Manual Other User', 'user', true)
    on conflict (id) do update
    set display_name = excluded.display_name,
        role         = excluded.role,
        is_active    = excluded.is_active;

    insert into public.conversations (id, user_id, title, language)
    values (other_conversation_id, other_user_id, 'Seed: private conversation owned by another user', 'vi')
    on conflict (id) do update
    set title      = excluded.title,
        language   = excluded.language,
        updated_at = timezone('utc', now());

    insert into public.messages (id, conversation_id, role, content, response_type, metadata)
    values
      (
        other_user_message_id,
        other_conversation_id,
        'user',
        'Conversation này dùng để test user khác không được xem.',
        null,
        '{"seed": true, "source": "manual_test"}'::jsonb
      ),
      (
        other_assistant_message_id,
        other_conversation_id,
        'assistant',
        'Private seeded assistant message — chỉ other user thấy được.',
        'text',
        '{"engine": "mock", "query_mode": "seed:manual", "execution_time_ms": 0, "source_count": 0, "seed": true}'::jsonb
      )
    on conflict (id) do update
    set content       = excluded.content,
        response_type = excluded.response_type,
        metadata      = excluded.metadata;

  end if;  -- end other_user_id block

  -- ── Admin user ───────────────────────────────────────────────────────────
  if admin_user_id is null then
    raise notice 'SKIP: auth user manual.admin@example.com not found. Create it in Supabase Auth first.';
  else
    insert into public.profiles (id, display_name, role, is_active)
    values (admin_user_id, 'Manual Admin', 'admin', true)
    on conflict (id) do update
    set display_name = excluded.display_name,
        role         = excluded.role,
        is_active    = excluded.is_active;
  end if;

  -- ── Inactive user ────────────────────────────────────────────────────────
  if inactive_user_id is null then
    raise notice 'SKIP: auth user manual.inactive@example.com not found. Create it in Supabase Auth first.';
  else
    insert into public.profiles (id, display_name, role, is_active)
    values (inactive_user_id, 'Manual Inactive User', 'user', false)
    on conflict (id) do update
    set display_name = excluded.display_name,
        role         = excluded.role,
        is_active    = excluded.is_active;
  end if;

end $$;
