-- Sprint 1 — Foundation: RBAC (reviewer), User Preferences, Version Metadata
-- Sprint 1 / S1-ARCH-01, S1-BE-01, S1-BE-02, S1-BE-03
--
-- Redo:
--   Run this file with `supabase db push` or in the Supabase SQL Editor.
--
-- Rollback:
--   Run backend/migrations/supabase/rollbacks/202606120001_sprint1_rbac_preferences_versions_down.sql.

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Extend profiles.role CHECK to include 'reviewer'
-- ─────────────────────────────────────────────────────────────────────────────
-- Drop old constraint and recreate with the full role set.
alter table public.profiles
    drop constraint if exists profiles_role_check;

alter table public.profiles
    add constraint profiles_role_check
    check (role in ('user', 'reviewer', 'admin'));

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Security helper: is_reviewer()
-- ─────────────────────────────────────────────────────────────────────────────
create or replace function public.is_reviewer()
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
      and role in ('reviewer', 'admin')
      and is_active = true
  );
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. User Preferences table
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.user_preferences (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles(id) on delete cascade,
  language      text not null default 'vi'
                  check (language in ('vi', 'en')),
  explanation_level text not null default 'general'
                  check (explanation_level in ('general', 'detailed', 'expert')),
  answer_style  text not null default 'concise'
                  check (answer_style in ('concise', 'detailed')),
  created_at    timestamptz not null default timezone('utc', now()),
  updated_at    timestamptz not null default timezone('utc', now()),
  unique (user_id)
);

create trigger user_preferences_set_updated_at
before update on public.user_preferences
for each row execute function public.set_updated_at();

create index if not exists idx_user_preferences_user_id on public.user_preferences(user_id);

-- RLS for user_preferences
alter table public.user_preferences enable row level security;

create policy "prefs_select_own"
on public.user_preferences
for select
using (user_id = auth.uid() or public.is_admin());

create policy "prefs_insert_own"
on public.user_preferences
for insert
with check (user_id = auth.uid());

create policy "prefs_update_own"
on public.user_preferences
for update
using (user_id = auth.uid())
with check (user_id = auth.uid());

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Update review_items RLS: allow reviewer to select pending items
-- ─────────────────────────────────────────────────────────────────────────────
-- Drop old admin-only policy and replace with reviewer-inclusive policy.
drop policy if exists "review_items_select_admin" on public.review_items;

create policy "review_items_select_reviewer_or_admin"
on public.review_items
for select
using (public.is_reviewer());

-- Keep admin-only update policy as-is (reviewers cannot resolve yet — Sprint 4).

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Extend review_items with resolution fields (Sprint 1 schema prep)
-- ─────────────────────────────────────────────────────────────────────────────
alter table public.review_items
    add column if not exists resolution_type text
        check (resolution_type is null or
               resolution_type in ('kg_fix', 'prompt_fix', 'no_action', 'duplicate')),
    add column if not exists resolution_note text;
