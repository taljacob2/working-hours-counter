-- ============================================================
-- Work Hours Logger — Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor → New query
-- ============================================================

-- 1. Work logs table
create table public.work_logs (
  id          text        primary key,
  platform    text        not null check (platform in ('office', 'home')),
  action      text        not null check (action in ('resume', 'pause')),
  timestamp   timestamptz not null,
  date_key    text        not null,   -- 'YYYY-MM-DD' local date
  created_at  timestamptz not null default now(),
  note        text        default ''
);

-- Enable Row Level Security
alter table public.work_logs enable row level security;

-- Policy: authenticated users have full access
create policy "Auth users full access"
  on public.work_logs
  for all
  to authenticated
  using (true)
  with check (true);

-- Index for date-range queries
create index work_logs_date_key_idx on public.work_logs (date_key);

-- ============================================================

-- 2. Settings table
create table public.work_settings (
  key   text primary key,
  value text not null
);

alter table public.work_settings enable row level security;

create policy "Auth users full access"
  on public.work_settings
  for all
  to authenticated
  using (true)
  with check (true);
