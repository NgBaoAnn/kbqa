-- Manual rollback for backend/migrations/supabase/versions/202606110001_app_core_schema.sql.
--
-- Warning:
--   This drops all app-core data. Back up the project before running on any
--   environment that contains real users, conversations or feedback.

drop trigger if exists on_auth_user_created on auth.users;

drop table if exists public.review_items cascade;
drop table if exists public.query_logs cascade;
drop table if exists public.feedback cascade;
drop table if exists public.message_sources cascade;
drop table if exists public.messages cascade;
drop table if exists public.conversations cascade;
drop table if exists public.profiles cascade;

drop function if exists public.owns_message(uuid);
drop function if exists public.owns_conversation(uuid);
drop function if exists public.is_admin();
drop function if exists public.handle_new_user();
drop function if exists public.set_updated_at();
