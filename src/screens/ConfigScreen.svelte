<script>
  import { initSupabase } from '../lib/supabase.js'
  import { screen, loading, showToast } from '../stores/appStore.js'
  import PasswordVisibilityToggle from '../components/PasswordVisibilityToggle.svelte'

  let url = localStorage.getItem('whl_sb_url') || ''
  let key = localStorage.getItem('whl_sb_key') || ''
  let showKey = false
  let error = ''

  const SQL = `-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor)
-- Multi-user: each account's rows are isolated by user_id via RLS, so
-- multiple people can sign up and use this same project independently.

create table public.work_logs (
  id text primary key,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  platform text not null check (platform in ('office','home')),
  action text not null check (action in ('resume','pause')),
  timestamp timestamptz not null,
  date_key text not null,
  created_at timestamptz not null default now(),
  note text default ''
);
alter table public.work_logs enable row level security;
create policy "own rows only" on public.work_logs
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

create table public.work_settings (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  key text not null,
  value text not null,
  primary key (user_id, key)
);
alter table public.work_settings enable row level security;
create policy "own rows only" on public.work_settings
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

create table public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  created_at timestamptz not null default now()
);
alter table public.push_subscriptions enable row level security;
create policy "own rows only" on public.push_subscriptions
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

create table public.rebalance_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  month_key text not null,
  applied_at timestamptz not null default now(),
  delta jsonb not null,
  summary jsonb not null
);
alter table public.rebalance_history enable row level security;
create policy "own rows only" on public.rebalance_history
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- Grant explicit permissions
grant usage on schema public to anon, authenticated, service_role;
grant select, insert, update, delete on table public.work_logs to anon, authenticated, service_role;
grant select, insert, update, delete on table public.work_settings to anon, authenticated, service_role;
grant select, insert, update, delete on table public.push_subscriptions to anon, authenticated, service_role;
grant select, insert, update, delete on table public.rebalance_history to anon, authenticated, service_role;`

  let copied = false
  function copySQL() {
    navigator.clipboard.writeText(SQL)
    copied = true
    setTimeout(() => copied = false, 2000)
  }

  async function connect() {
    error = ''
    if (!url.trim() || !key.trim()) { error = 'Both fields are required.'; return }
    loading.set(true)
    try {
      const sb = initSupabase(url.trim(), key.trim())
      // Validate connectivity using auth (no table access = RLS-safe)
      const { error: authErr } = await sb.auth.getSession()
      if (authErr) throw authErr
      localStorage.setItem('whl_sb_url', url.trim())
      localStorage.setItem('whl_sb_key', key.trim())
      screen.set('signin')
    } catch (e) {
      error = e.message || 'Could not connect. Check your URL and anon key.'
    } finally {
      loading.set(false)
    }
  }
</script>

<div class="auth-page">
  <div class="auth-card">
    <div class="auth-logo">⏱</div>
    <h1>Work Hours Logger</h1>
    <p class="auth-subtitle">Connect your Supabase project to get started.</p>

    <!-- Step 1 -->
    <div class="step">
      <div class="step-num">1</div>
      <div>
        <strong>Create a Supabase project</strong> at
        <a href="https://supabase.com" target="_blank" rel="noreferrer">supabase.com</a>
      </div>
    </div>
    <div class="step">
      <div class="step-num">2</div>
      <div>Go to <strong>SQL Editor</strong> and run the schema below</div>
    </div>
    <div class="step">
      <div class="step-num">3</div>
      <div>Paste your <strong>Project URL</strong> and <strong>Anon Key</strong> below</div>
    </div>

    <div class="sql-block">
      <div class="sql-header">
        <span>Schema SQL</span>
        <button class="btn btn-sm btn-secondary" on:click={copySQL}>
          {copied ? '✅ Copied' : '📋 Copy'}
        </button>
      </div>
      <pre>{SQL}</pre>
    </div>

    <form on:submit|preventDefault={connect}>
      <div class="field" style="margin-top:1.25rem">
        <label for="cfg-url">Supabase Project URL</label>
        <input id="cfg-url" type="url" bind:value={url} placeholder="https://xxxx.supabase.co" required autocomplete="off" />
      </div>
      <div class="field">
        <label for="cfg-key">Anon (public) Key</label>
        <div class="input-wrap">
          <input id="cfg-key" type={showKey ? 'text' : 'password'} bind:value={key} placeholder="eyJ…" required autocomplete="off" />
          <PasswordVisibilityToggle visible={showKey} on:click={() => showKey = !showKey} />
        </div>
        <span class="hint">Find these in Supabase Dashboard → Project Settings → API</span>
      </div>
      {#if error}<p class="form-error">{error}</p>{/if}
      <button type="submit" class="btn btn-primary btn-full" style="margin-top:1.25rem">
        Save &amp; Connect →
      </button>
    </form>
  </div>
</div>

<style>
  .auth-page {
    min-height: 100dvh;
    display: flex; align-items: center; justify-content: center;
    padding: 2rem 1rem;
    background: var(--color-bg);
  }
  .auth-card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: 2.5rem 2rem;
    width: 100%; max-width: 520px;
    box-shadow: var(--shadow-lg);
  }
  .auth-logo { font-size: 2.5rem; text-align: center; margin-bottom: 0.75rem; }
  h1 { text-align: center; font-size: 1.5rem; font-weight: 700; margin-bottom: 0.375rem; }
  .auth-subtitle { text-align: center; color: var(--color-text-muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
  .step { display: flex; align-items: flex-start; gap: 0.75rem; margin-bottom: 0.625rem; font-size: 0.875rem; }
  .step-num {
    flex-shrink: 0; width: 22px; height: 22px;
    background: var(--color-primary); color: #fff;
    border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem; font-weight: 700;
  }
  .sql-block { margin: 1rem 0; border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow: hidden; }
  .sql-header { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.75rem; background: var(--color-surface-2); font-size: 0.8rem; font-weight: 600; }
  pre { padding: 0.75rem; font-size: 0.72rem; line-height: 1.5; overflow-x: auto; color: var(--color-text); background: var(--color-bg); max-height: 180px; }
  .input-wrap { position: relative; }
  .input-wrap input { padding-right: 2.5rem; }
  .hint { font-size: 0.75rem; color: var(--color-text-muted); margin-top: 4px; display: block; }
  .form-error { color: var(--color-ot-neg); font-size: 0.875rem; margin-top: 0.5rem; }
</style>
