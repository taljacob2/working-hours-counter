-- ============================================================
-- Work Hours Logger — Cascade-delete migration
-- Run this in: Supabase Dashboard → SQL Editor → New query
-- Safe to re-run.
--
-- What this does: makes each user_id foreign key ON DELETE CASCADE, so
-- deleting an auth.users row (via the delete-account Edge Function)
-- automatically wipes that user's work_logs/work_settings/
-- push_subscriptions/rebalance_history rows too — no separate per-table
-- deletes needed. Looks up each constraint's real name dynamically
-- instead of assuming Postgres's default naming, since it's not
-- guaranteed to match across every project.
-- ============================================================

do $$
declare
  conname text;
  tbl text;
  tables text[] := array['work_logs', 'work_settings', 'push_subscriptions', 'rebalance_history'];
begin
  foreach tbl in array tables loop
    select tc.constraint_name into conname
    from information_schema.table_constraints tc
    join information_schema.key_column_usage kcu
      on tc.constraint_name = kcu.constraint_name and tc.table_schema = kcu.table_schema
    where tc.table_schema = 'public'
      and tc.table_name = tbl
      and tc.constraint_type = 'FOREIGN KEY'
      and kcu.column_name = 'user_id';

    if conname is not null then
      execute format('alter table public.%I drop constraint %I', tbl, conname);
    end if;

    execute format(
      'alter table public.%I add constraint %I_user_id_fkey foreign key (user_id) references auth.users(id) on delete cascade',
      tbl, tbl
    );
  end loop;
end $$;
