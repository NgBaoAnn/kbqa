-- AegisHealth KBQA manual test seed.
--
-- Run after:
--   1. backend/migrations/supabase/versions/202606110001_app_core_schema.sql
--   2. Creating the emails below in Supabase Auth.
--
-- This file is intentionally idempotent and does not insert into auth.users or
-- auth.identities. Supabase Auth remains the owner of registration/login.

do $$
declare
  normal_user_id uuid;
  other_user_id uuid;
  admin_user_id uuid;
  inactive_user_id uuid;
  normal_conversation_id uuid := '11111111-1111-4111-8111-111111111111';
  other_conversation_id uuid := '22222222-2222-4222-8222-222222222222';
  normal_user_message_id uuid := '33333333-3333-4333-8333-333333333333';
  normal_assistant_message_id uuid := '44444444-4444-4444-8444-444444444444';
  normal_query_log_id uuid := '77777777-7777-4777-8777-777777777777';
  other_user_message_id uuid := '55555555-5555-4555-8555-555555555555';
  other_assistant_message_id uuid := '66666666-6666-4666-8666-666666666666';
begin
  select id into normal_user_id from auth.users where email = 'manual.user@example.com';
  select id into other_user_id from auth.users where email = 'manual.other@example.com';
  select id into admin_user_id from auth.users where email = 'manual.admin@example.com';
  select id into inactive_user_id from auth.users where email = 'manual.inactive@example.com';

  if normal_user_id is null then
    raise notice 'Missing auth user manual.user@example.com; skipping normal-user seed.';
  else
    insert into public.profiles (id, display_name, role, is_active)
    values (normal_user_id, 'Manual User', 'user', true)
    on conflict (id) do update
    set display_name = excluded.display_name,
        role = excluded.role,
        is_active = excluded.is_active;

    insert into public.conversations (id, user_id, title, language)
    values (
      normal_conversation_id,
      normal_user_id,
      'Seed: tư vấn đau đầu',
      'vi'
    )
    on conflict (id) do update
    set title = excluded.title,
        language = excluded.language,
        updated_at = timezone('utc', now());

    insert into public.messages (
      id,
      conversation_id,
      role,
      content,
      response_type,
      data,
      safety,
      metadata
    )
    values
      (
        normal_user_message_id,
        normal_conversation_id,
        'user',
        'Đau đầu kéo dài có nguy hiểm không?',
        null,
        null,
        null,
        '{"seed": true, "source": "manual_test"}'::jsonb
      ),
      (
        normal_assistant_message_id,
        normal_conversation_id,
        'assistant',
        'Đây là câu trả lời mẫu cho Sprint 1. Nếu đau đầu dữ dội, đột ngột hoặc kèm yếu liệt, sốt cao, nôn ói kéo dài, người bệnh nên đi khám ngay.',
        'text',
        null,
        '{"level": "caution", "requires_emergency_notice": false, "disclaimer": "Thông tin chỉ mang tính chất tham khảo."}'::jsonb,
        '{"engine": "mock", "query_mode": "seed:manual", "execution_time_ms": 0, "source_count": 0, "seed": true}'::jsonb
      )
    on conflict (id) do update
    set content = excluded.content,
        response_type = excluded.response_type,
        data = excluded.data,
        safety = excluded.safety,
        metadata = excluded.metadata;

    insert into public.query_logs (
      id,
      message_id,
      engine,
      query_mode,
      execution_time_ms,
      source_count,
      status,
      metadata
    )
    values (
      normal_query_log_id,
      normal_assistant_message_id,
      'mock',
      'seed:manual',
      0,
      0,
      'success',
      '{"seed": true, "ai_called": false}'::jsonb
    )
    on conflict (id) do update
    set message_id = excluded.message_id,
        engine = excluded.engine,
        query_mode = excluded.query_mode,
        execution_time_ms = excluded.execution_time_ms,
        source_count = excluded.source_count,
        status = excluded.status,
        metadata = excluded.metadata;
  end if;

  if other_user_id is null then
    raise notice 'Missing auth user manual.other@example.com; skipping other-user seed.';
  else
    insert into public.profiles (id, display_name, role, is_active)
    values (other_user_id, 'Manual Other User', 'user', true)
    on conflict (id) do update
    set display_name = excluded.display_name,
        role = excluded.role,
        is_active = excluded.is_active;

    insert into public.conversations (id, user_id, title, language)
    values (
      other_conversation_id,
      other_user_id,
      'Seed: private conversation owned by another user',
      'vi'
    )
    on conflict (id) do update
    set title = excluded.title,
        language = excluded.language,
        updated_at = timezone('utc', now());

    insert into public.messages (
      id,
      conversation_id,
      role,
      content,
      response_type,
      metadata
    )
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
        'Private seeded assistant message.',
        'text',
        '{"engine": "mock", "query_mode": "seed:manual", "execution_time_ms": 0, "source_count": 0, "seed": true}'::jsonb
      )
    on conflict (id) do update
    set content = excluded.content,
        response_type = excluded.response_type,
        metadata = excluded.metadata;
  end if;

  if admin_user_id is null then
    raise notice 'Missing auth user manual.admin@example.com; skipping admin profile seed.';
  else
    insert into public.profiles (id, display_name, role, is_active)
    values (admin_user_id, 'Manual Admin', 'admin', true)
    on conflict (id) do update
    set display_name = excluded.display_name,
        role = excluded.role,
        is_active = excluded.is_active;
  end if;

  if inactive_user_id is null then
    raise notice 'Missing auth user manual.inactive@example.com; skipping inactive profile seed.';
  else
    insert into public.profiles (id, display_name, role, is_active)
    values (inactive_user_id, 'Manual Inactive User', 'user', false)
    on conflict (id) do update
    set display_name = excluded.display_name,
        role = excluded.role,
        is_active = excluded.is_active;
  end if;
end $$;
