-- AegisHealth KBQA app-core schema for Supabase.
-- Sprint 1 / S1-ARCH-02
--
-- Redo:
--   Run this file with `supabase db push` or in the Supabase SQL Editor.
--
-- Rollback:
--   Run backend/migrations/supabase/rollbacks/202606110001_app_core_schema_down.sql.

create extension if not exists pgcrypto with schema extensions;

-- Shared updated_at trigger.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

-- App profile mapped 1:1 to Supabase Auth users.
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  role text not null default 'user' check (role in ('user', 'admin')),
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name, role)
  values (
    new.id,
    coalesce(
      new.raw_user_meta_data ->> 'display_name',
      split_part(new.email, '@', 1),
      'User'
    ),
    'user'
  )
  on conflict (id) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  title text not null default 'Cuộc trò chuyện mới',
  language text not null default 'vi' check (language in ('vi', 'en')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create trigger conversations_set_updated_at
before update on public.conversations
for each row execute function public.set_updated_at();

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  response_type text check (
    response_type is null
    or response_type in ('text', 'table', 'warning', 'disambiguation', 'source_list')
  ),
  data jsonb,
  safety jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.message_sources (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.messages(id) on delete cascade,
  source_type text not null check (
    source_type in (
      'cypher',
      'neo4j',
      'lightrag_entity',
      'lightrag_relationship',
      'lightrag_chunk',
      'document',
      'other'
    )
  ),
  title text not null,
  snippet text,
  metadata jsonb not null default '{}'::jsonb,
  rank int not null default 1 check (rank > 0),
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.messages(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  rating text not null check (rating in ('up', 'down')),
  reason text check (
    reason is null
    or reason in ('helpful', 'incorrect', 'unsafe', 'unclear', 'incomplete', 'other')
  ),
  comment text,
  created_at timestamptz not null default timezone('utc', now()),
  unique (message_id, user_id)
);

create table if not exists public.query_logs (
  id uuid primary key default gen_random_uuid(),
  message_id uuid references public.messages(id) on delete set null,
  engine text not null check (engine in ('cypher_direct', 'lightrag', 'mock', 'unknown')),
  query_mode text,
  execution_time_ms double precision not null default 0 check (execution_time_ms >= 0),
  source_count int not null default 0 check (source_count >= 0),
  status text not null default 'success' check (status in ('success', 'error', 'timeout')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.review_items (
  id uuid primary key default gen_random_uuid(),
  feedback_id uuid not null references public.feedback(id) on delete cascade,
  status text not null default 'pending' check (status in ('pending', 'in_review', 'resolved', 'dismissed')),
  category text not null default 'answer_quality' check (
    category in ('answer_quality', 'knowledge_gap', 'safety', 'bug', 'feature_request', 'other')
  ),
  assignee_id uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  resolved_at timestamptz
);

create index if not exists idx_profiles_role on public.profiles(role);
create index if not exists idx_conversations_user_updated on public.conversations(user_id, updated_at desc);
create index if not exists idx_messages_conversation_created on public.messages(conversation_id, created_at);
create index if not exists idx_message_sources_message_rank on public.message_sources(message_id, rank);
create index if not exists idx_feedback_user_created on public.feedback(user_id, created_at desc);
create index if not exists idx_feedback_message_user on public.feedback(message_id, user_id);
create index if not exists idx_query_logs_created on public.query_logs(created_at desc);
create index if not exists idx_query_logs_engine_status on public.query_logs(engine, status);
create index if not exists idx_review_items_status_created on public.review_items(status, created_at desc);

-- Security helper functions.
create or replace function public.is_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.profiles
    where id = auth.uid()
      and role = 'admin'
      and is_active = true
  );
$$;

create or replace function public.owns_conversation(conversation_uuid uuid)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.conversations
    where id = conversation_uuid
      and user_id = auth.uid()
  );
$$;

create or replace function public.owns_message(message_uuid uuid)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.messages m
    join public.conversations c on c.id = m.conversation_id
    where m.id = message_uuid
      and c.user_id = auth.uid()
  );
$$;

-- Enable RLS for all application tables.
alter table public.profiles enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.message_sources enable row level security;
alter table public.feedback enable row level security;
alter table public.query_logs enable row level security;
alter table public.review_items enable row level security;

-- profiles
create policy "profiles_select_own_or_admin"
on public.profiles
for select
using (id = auth.uid() or public.is_admin());

create policy "profiles_insert_own"
on public.profiles
for insert
with check (id = auth.uid());

create policy "profiles_update_admin"
on public.profiles
for update
using (public.is_admin())
with check (public.is_admin());

-- conversations
create policy "conversations_select_own_or_admin"
on public.conversations
for select
using (user_id = auth.uid() or public.is_admin());

create policy "conversations_insert_own"
on public.conversations
for insert
with check (user_id = auth.uid());

create policy "conversations_update_own_or_admin"
on public.conversations
for update
using (user_id = auth.uid() or public.is_admin())
with check (user_id = auth.uid() or public.is_admin());

create policy "conversations_delete_own_or_admin"
on public.conversations
for delete
using (user_id = auth.uid() or public.is_admin());

-- messages
create policy "messages_select_own_or_admin"
on public.messages
for select
using (public.owns_conversation(conversation_id) or public.is_admin());

create policy "messages_insert_user_owned_conversation"
on public.messages
for insert
with check (
  role = 'user'
  and public.owns_conversation(conversation_id)
);

-- Assistant/system messages are written by backend service role.

-- message_sources
create policy "message_sources_select_own_or_admin"
on public.message_sources
for select
using (public.owns_message(message_id) or public.is_admin());

-- Sources are written by backend service role.

-- feedback
create policy "feedback_select_own_or_admin"
on public.feedback
for select
using (user_id = auth.uid() or public.is_admin());

create policy "feedback_insert_own_for_owned_message"
on public.feedback
for insert
with check (
  user_id = auth.uid()
  and public.owns_message(message_id)
);

create policy "feedback_update_own_or_admin"
on public.feedback
for update
using (user_id = auth.uid() or public.is_admin())
with check (user_id = auth.uid() or public.is_admin());

-- query_logs
create policy "query_logs_select_admin"
on public.query_logs
for select
using (public.is_admin());

-- Logs are written by backend service role.

-- review_items
create policy "review_items_select_admin"
on public.review_items
for select
using (public.is_admin());

create policy "review_items_update_admin"
on public.review_items
for update
using (public.is_admin())
with check (public.is_admin());

-- Review items are written by backend service role when negative feedback is submitted.
