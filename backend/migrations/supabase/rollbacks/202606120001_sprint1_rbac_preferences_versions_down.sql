-- Rollback for 202606120001_sprint1_rbac_preferences_versions.sql

-- Remove resolution fields from review_items
alter table public.review_items
    drop column if exists resolution_type,
    drop column if exists resolution_note;

-- Restore review_items select policy (admin-only)
drop policy if exists "review_items_select_reviewer_or_admin" on public.review_items;

create policy "review_items_select_admin"
on public.review_items
for select
using (public.is_admin());

-- Drop user_preferences table
drop policy if exists "prefs_update_own" on public.user_preferences;
drop policy if exists "prefs_insert_own" on public.user_preferences;
drop policy if exists "prefs_select_own" on public.user_preferences;
drop table if exists public.user_preferences;

-- Drop is_reviewer function
drop function if exists public.is_reviewer();

-- Restore profiles.role CHECK to user/admin only
alter table public.profiles
    drop constraint if exists profiles_role_check;

alter table public.profiles
    add constraint profiles_role_check
    check (role in ('user', 'admin'));
