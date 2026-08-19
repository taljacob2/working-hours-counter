<script>
  import { getSupabase } from '../lib/supabase.js'
  import { screen, user, logs, requiredHours, minimumDailyHours, use24HourFormat, loading, showToast } from '../stores/appStore.js'
  import { byTs } from '../lib/timeUtils.js'
  import { OAUTH_PROVIDERS, hasEnabledOAuthProvider } from '../lib/authProviders.js'
  import PasswordVisibilityToggle from '../components/PasswordVisibilityToggle.svelte'

  let email = ''
  let password = ''
  let error = ''
  let info = ''
  let busy = false
  let mode = 'signin' // 'signin' | 'signup'
  let showPassword = false

  function switchMode(next) {
    mode = next
    error = ''
    info = ''
  }

  async function submit() {
    if (mode === 'signup') return signUp()
    return signIn()
  }

  // OAuth is a full-page redirect — Supabase sends the browser to the
  // provider, then back to redirectTo with the session already in the URL.
  // App.svelte's onMount already calls getSession()/loadAll() on load, so
  // no extra handling is needed here once the redirect lands back on the app.
  async function signInWithProvider(provider) {
    error = ''
    const sb = getSupabase()
    const { error: err } = await sb.auth.signInWithOAuth({
      provider,
      options: { redirectTo: window.location.origin + import.meta.env.BASE_URL },
    })
    if (err) error = err.message
  }

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

  async function signUp() {
    error = ''
    info = ''
    busy = true
    const sb = getSupabase()
    const { data, error: err } = await sb.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: window.location.origin + import.meta.env.BASE_URL },
    })
    if (err) { error = err.message; busy = false; return }

    if (data.session) {
      // Email confirmation is disabled on this project — signUp already
      // returned a live session, so go straight in like a normal sign-in.
      user.set(data.user)
      try {
        await loadAll(sb)
        screen.set('main')
      } catch (e) {
        error = e.message || 'Failed to load data after sign up.'
      } finally {
        busy = false
      }
      return
    }

    // Email confirmation is required — no session yet, account exists but
    // is inactive until the user clicks the link Supabase just emailed them.
    info = 'Account created — check your email to confirm it, then sign in.'
    mode = 'signin'
    password = ''
    busy = false
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
      const use24Val = settings?.find(s => s.key === 'use24HourFormat')?.value

      requiredHours.set(parseFloat(reqVal ?? localStorage.getItem('whl_req_hours') ?? '9'))
      minimumDailyHours.set(parseFloat(minVal ?? localStorage.getItem('whl_min_hours') ?? '5'))

      const local24 = localStorage.getItem('whl_24h_format')
      use24HourFormat.set(use24Val ? use24Val === 'true' : (local24 ? local24 === 'true' : true))
    } finally {
      loading.set(false)
    }
  }
</script>

<div class="auth-page">
  <div class="auth-card">
    <div class="auth-logo">⏱</div>
    <h1>Work Hours Logger</h1>
    <p class="auth-subtitle">{mode === 'signup' ? 'Create an account to start tracking your hours.' : 'Sign in to access your logs.'}</p>

    <form on:submit|preventDefault={submit}>
      <div class="field">
        <label for="si-email">Email</label>
        <input id="si-email" type="email" bind:value={email} placeholder="you@example.com" required autocomplete="email" />
      </div>
      <div class="field">
        <label for="si-password">Password</label>
        <div class="password-input-wrap">
          <input id="si-password" type={showPassword ? 'text' : 'password'} bind:value={password} placeholder="••••••••" required autocomplete={mode === 'signup' ? 'new-password' : 'current-password'} minlength={mode === 'signup' ? 6 : undefined} />
          <PasswordVisibilityToggle visible={showPassword} on:click={() => showPassword = !showPassword} />
        </div>
      </div>
      {#if error}<p class="form-error">⚠️ {error}</p>{/if}
      {#if info}<p class="form-info">✅ {info}</p>{/if}
      <button type="submit" class="btn btn-primary btn-full" disabled={busy} style="margin-top:1.25rem">
        {#if busy}
          <span class="spin"></span> {mode === 'signup' ? 'Creating account…' : 'Signing in…'}
        {:else}
          {mode === 'signup' ? 'Create account →' : 'Sign in →'}
        {/if}
      </button>
    </form>

    {#if hasEnabledOAuthProvider}
      <div class="oauth-divider"><span>or</span></div>
      <div class="oauth-buttons">
        {#if OAUTH_PROVIDERS.google}
          <button type="button" class="btn btn-secondary btn-full" on:click={() => signInWithProvider('google')}>
            Continue with Google
          </button>
        {/if}
        {#if OAUTH_PROVIDERS.github}
          <button type="button" class="btn btn-secondary btn-full" on:click={() => signInWithProvider('github')}>
            Continue with GitHub
          </button>
        {/if}
      </div>
    {/if}

    <p class="reconfigure-hint">
      {#if mode === 'signup'}
        Already have an account?
        <button class="link-btn" on:click={() => switchMode('signin')}>Sign in</button>
      {:else}
        New here?
        <button class="link-btn" on:click={() => switchMode('signup')}>Create an account</button>
      {/if}
    </p>

    {#if !import.meta.env.NEXT_PUBLIC_SUPABASE_URL}
      <p class="reconfigure-hint">
        Wrong project?
        <button class="link-btn" on:click={() => { localStorage.removeItem('whl_sb_url'); localStorage.removeItem('whl_sb_key'); screen.set('config') }}>
          Reconfigure
        </button>
      </p>
    {/if}
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
  .password-input-wrap { position: relative; }
  .password-input-wrap input { padding-right: 2.25rem; }
  .form-error { color: var(--color-ot-neg); font-size: 0.875rem; margin-top: 0.5rem; }
  .form-info { color: var(--color-primary); font-size: 0.875rem; margin-top: 0.5rem; }
  .oauth-divider {
    display: flex; align-items: center; gap: 0.75rem;
    margin: 1.25rem 0; color: var(--color-text-muted); font-size: 0.75rem;
  }
  .oauth-divider::before, .oauth-divider::after {
    content: ''; flex: 1; height: 1px; background: var(--color-border);
  }
  .oauth-buttons { display: flex; flex-direction: column; gap: 0.5rem; }
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
