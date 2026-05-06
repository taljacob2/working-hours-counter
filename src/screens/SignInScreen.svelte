<script>
  import { getSupabase } from '../lib/supabase.js'
  import { screen, user, logs, requiredHours, minimumDailyHours, loading, showToast } from '../stores/appStore.js'
  import { byTs } from '../lib/timeUtils.js'

  let email = ''
  let password = ''
  let error = ''
  let busy = false

  async function signIn() {
    error = ''
    busy = true
    const sb = getSupabase()
    const { data, error: err } = await sb.auth.signInWithPassword({ email, password })
    if (err) { error = err.message; busy = false; return }
    user.set(data.user)
    
    try {
      await loadAll(sb)
      screen.set('main')
    } catch (e) {
      error = e.message || 'Failed to load data after sign in.'
    } finally {
      busy = false
    }
  }

  async function loadAll(sb) {
    loading.set(true)
    try {
      const { data: logData, error: logErr } = await sb
        .from('work_logs').select('*').order('timestamp', { ascending: true })
      if (logErr) throw logErr
      logs.set(logData || [])

      const { data: settings } = await sb.from('work_settings').select('key, value')
      const reqVal = settings?.find(s => s.key === 'requiredDailyHours')?.value
      const minVal = settings?.find(s => s.key === 'minimumDailyHours')?.value

      requiredHours.set(parseFloat(reqVal ?? localStorage.getItem('whl_req_hours') ?? '9'))
      minimumDailyHours.set(parseFloat(minVal ?? localStorage.getItem('whl_min_hours') ?? '5'))
    } finally {
      loading.set(false)
    }
  }
</script>

<div class="auth-page">
  <div class="auth-card">
    <div class="auth-logo">⏱</div>
    <h1>Work Hours Logger</h1>
    <p class="auth-subtitle">Sign in to access your logs.</p>

    <form on:submit|preventDefault={signIn}>
      <div class="field">
        <label for="si-email">Email</label>
        <input id="si-email" type="email" bind:value={email} placeholder="you@example.com" required autocomplete="email" />
      </div>
      <div class="field">
        <label for="si-password">Password</label>
        <input id="si-password" type="password" bind:value={password} placeholder="••••••••" required autocomplete="current-password" />
      </div>
      {#if error}<p class="form-error">⚠️ {error}</p>{/if}
      <button type="submit" class="btn btn-primary btn-full" disabled={busy} style="margin-top:1.25rem">
        {#if busy}
          <span class="spin"></span> Signing in…
        {:else}
          Sign in →
        {/if}
      </button>
    </form>

    <p class="reconfigure-hint">
      Wrong project?
      <button class="link-btn" on:click={() => { localStorage.removeItem('whl_sb_url'); localStorage.removeItem('whl_sb_key'); screen.set('config') }}>
        Reconfigure
      </button>
    </p>
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
    width: 100%; max-width: 420px;
    box-shadow: var(--shadow-lg);
  }
  .auth-logo { font-size: 2.5rem; text-align: center; margin-bottom: 0.75rem; }
  h1 { text-align: center; font-size: 1.5rem; font-weight: 700; margin-bottom: 0.375rem; }
  .auth-subtitle { text-align: center; color: var(--color-text-muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
  .form-error { color: var(--color-ot-neg); font-size: 0.875rem; margin-top: 0.5rem; }
  .reconfigure-hint { text-align: center; font-size: 0.8rem; color: var(--color-text-muted); margin-top: 1.25rem; }
  .link-btn { background: none; border: none; color: var(--color-primary); cursor: pointer; font-size: 0.8rem; text-decoration: underline; }
  .spin {
    display: inline-block; width: 14px; height: 14px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
