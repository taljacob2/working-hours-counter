-- ============================================================
-- Work Hours Logger — Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor → New query
-- Safe to re-run: all statements use IF NOT EXISTS / IF EXISTS guards
-- ============================================================

-- 1. Work logs table
create table if not exists public.work_logs (
  id          text        primary key,
  platform    text        not null check (platform in ('office', 'home')),
  action      text        not null check (action in ('resume', 'pause')),
  timestamp   timestamptz not null,
  date_key    text        not null,   -- 'YYYY-MM-DD' local date
  created_at  timestamptz not null default now(),
  note        text        default ''
);

alter table public.work_logs enable row level security;

create policy if not exists "Auth users full access"
  on public.work_logs
  for all
  to authenticated
  using (true)
  with check (true);

create index if not exists work_logs_date_key_idx on public.work_logs (date_key);

-- ============================================================

-- 2. Settings table
create table if not exists public.work_settings (
  key   text primary key,
  value text not null
);

alter table public.work_settings enable row level security;

create policy if not exists "Auth users full access"
  on public.work_settings
  for all
  to authenticated
  using (true)
  with check (true);

-- ============================================================

-- 3. Rebalance history table
create table if not exists public.rebalance_history (
  id          uuid        primary key default gen_random_uuid(),
  user_id     uuid        not null references auth.users(id),
  month_key   text        not null,   -- 'YYYY-MM'
  applied_at  timestamptz not null default now(),
  delta       jsonb       not null,   -- { inserted_ids, updated, deleted_logs }
  summary     jsonb       not null    -- { updates, inserts, deletes, otBefore, otAfter, dateKeys }
);

alter table public.rebalance_history enable row level security;

create policy if not exists "own rows only"
  on public.rebalance_history
  for all
  using  (user_id = auth.uid())
  with check (user_id = auth.uid());

create index if not exists rebalance_history_user_month_idx
  on public.rebalance_history (user_id, month_key, applied_at);

-- ============================================================

-- 4. Explicit permissions (fixes "permission denied" errors)
grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on table public.work_logs to anon, authenticated;
grant select, insert, update, delete on table public.work_settings to anon, authenticated;
grant select, insert, update, delete on table public.rebalance_history to anon, authenticated;
