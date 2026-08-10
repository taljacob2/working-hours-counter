-- ============================================================
-- Work Hours Logger — Multi-user migration
-- Run this in: Supabase Dashboard → SQL Editor → New query
-- Safe to re-run: every step is idempotent (if not exists / where null / drop if exists)
--
-- What this does: adds a `user_id` column (defaulting to the signed-in
-- user via auth.uid()) to work_logs, work_settings, and push_subscriptions,
-- backfills existing rows to the current account, and replaces the
-- "any authenticated user, all rows" RLS policies with "own rows only" —
-- the same pattern rebalance_history already uses. This is what turns the
-- app from single-tenant (anyone who signs in sees the same data) into
-- multi-tenant (each account gets its own isolated logs/settings/history).
--
-- IMPORTANT: change the email below to the account that owns the data
-- already in these tables, before running.
-- ============================================================

do $$
declare
  owner_id uuid;
begin
  select id into owner_id from auth.users where email = 'taljacob2@gmail.com';
  if owner_id is null then
    raise exception 'No auth.users row found for that email — update the email in this script before running.';
  end if;

  -- 1. work_logs ------------------------------------------------
  alter table public.work_logs add column if not exists user_id uuid references auth.users(id);
  update public.work_logs set user_id = owner_id where user_id is null;
  alter table public.work_logs alter column user_id set not null;
  alter table public.work_logs alter column user_id set default auth.uid();

  -- 2. work_settings ---------------------------------------------
  -- key alone can no longer be the primary key once multiple users each
  -- have their own requiredDailyHours/notifDeliverVia/etc — becomes (user_id, key).
  alter table public.work_settings add column if not exists user_id uuid references auth.users(id);
  update public.work_settings set user_id = owner_id where user_id is null;
  alter table public.work_settings alter column user_id set not null;
  alter table public.work_settings alter column user_id set default auth.uid();
  alter table public.work_settings drop constraint if exists work_settings_pkey;
  alter table public.work_settings add primary key (user_id, key);

  -- 3. push_subscriptions ------------------------------------------
  alter table public.push_subscriptions add column if not exists user_id uuid references auth.users(id);
  update public.push_subscriptions set user_id = owner_id where user_id is null;
  alter table public.push_subscriptions alter column user_id set not null;
  alter table public.push_subscriptions alter column user_id set default auth.uid();
end $$;

create index if not exists work_logs_user_id_idx on public.work_logs (user_id);
create index if not exists push_subscriptions_user_id_idx on public.push_subscriptions (user_id);

-- ============================================================
-- Replace "any authenticated user, all rows" policies with per-user ones
-- ============================================================

drop policy if exists "Auth users full access" on public.work_logs;
create policy "own rows only" on public.work_logs
  for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "Auth users full access" on public.work_settings;
create policy "own rows only" on public.work_settings
  for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "Auth users full access" on public.push_subscriptions;
create policy "own rows only" on public.push_subscriptions
  for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
