-- ============================================================
-- Work Hours Logger — Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor → New query
-- Safe to re-run: uses IF NOT EXISTS and exception-safe DO blocks
-- ============================================================

-- 1. Work logs table
-- user_id defaults to auth.uid() so every insert from a signed-in browser is
-- automatically attributed to that account with no client-side code needed;
-- the RLS policy below then keeps each account's rows fully isolated.
create table if not exists public.work_logs (
  id          text        primary key,
  user_id     uuid        not null default auth.uid() references auth.users(id),
  platform    text        not null check (platform in ('office', 'home')),
  action      text        not null check (action in ('resume', 'pause')),
  timestamp   timestamptz not null,
  date_key    text        not null,   -- 'YYYY-MM-DD' local date
  created_at  timestamptz not null default now(),
  note        text        default ''
);

alter table public.work_logs enable row level security;

do $$ begin
  create policy "own rows only"
    on public.work_logs for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());
exception when duplicate_object then null;
end $$;

create index if not exists work_logs_date_key_idx on public.work_logs (date_key);
create index if not exists work_logs_user_id_idx on public.work_logs (user_id);

-- ============================================================

-- 2. Settings table (flat key/value, one row per setting per user)
create table if not exists public.work_settings (
  user_id uuid not null default auth.uid() references auth.users(id),
  key     text not null,
  value   text not null,
  primary key (user_id, key)
);

alter table public.work_settings enable row level security;

do $$ begin
  create policy "own rows only"
    on public.work_settings for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());
exception when duplicate_object then null;
end $$;

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

do $$ begin
  create policy "own rows only"
    on public.rebalance_history for all
    using  (user_id = auth.uid())
    with check (user_id = auth.uid());
exception when duplicate_object then null;
end $$;

create index if not exists rebalance_history_user_month_idx
  on public.rebalance_history (user_id, month_key, applied_at);

-- ============================================================

-- 4. Web Push subscriptions (installed PWA notification delivery)
create table if not exists public.push_subscriptions (
  id         uuid        primary key default gen_random_uuid(),
  user_id    uuid        not null default auth.uid() references auth.users(id),
  endpoint   text        not null unique,
  p256dh     text        not null,
  auth       text        not null,
  created_at timestamptz not null default now()
);

alter table public.push_subscriptions enable row level security;

do $$ begin
  create policy "own rows only"
    on public.push_subscriptions for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());
exception when duplicate_object then null;
end $$;

create index if not exists push_subscriptions_user_id_idx on public.push_subscriptions (user_id);

-- ============================================================

-- 5. Explicit permissions (fixes "permission denied" errors)
-- service_role is included too: scripts/send-notifications.mjs authenticates
-- as service_role (no user session to act as authenticated with), and it
-- does NOT get implicit table access just from bypassing RLS.
grant usage on schema public to anon, authenticated, service_role;
grant select, insert, update, delete on table public.work_logs to anon, authenticated, service_role;
grant select, insert, update, delete on table public.work_settings to anon, authenticated, service_role;
grant select, insert, update, delete on table public.rebalance_history to anon, authenticated, service_role;
grant select, insert, update, delete on table public.push_subscriptions to anon, authenticated, service_role;
