<script>
  import { onMount } from 'svelte'
  import { screen, user, logs, requiredHours, loading, theme } from './stores/appStore.js'
  import { initSupabase, getSupabase } from './lib/supabase.js'

  import Spinner     from './components/Spinner.svelte'
  import Toast       from './components/Toast.svelte'
  import TopBar      from './components/TopBar.svelte'
  import ConfigScreen   from './screens/ConfigScreen.svelte'
  import SignInScreen   from './screens/SignInScreen.svelte'
  import MainScreen     from './screens/MainScreen.svelte'
  import LogsScreen     from './screens/LogsScreen.svelte'
  import SettingsScreen from './screens/SettingsScreen.svelte'

  onMount(async () => {
    // Apply saved theme
    const savedTheme = localStorage.getItem('whl_theme') ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    theme.set(savedTheme)
    document.documentElement.setAttribute('data-theme', savedTheme)

    // Check Supabase config
    const url = localStorage.getItem('whl_sb_url')
    const key = localStorage.getItem('whl_sb_key')
    if (!url || !key) { screen.set('config'); return }

    // Init client
    let sb
    try { sb = initSupabase(url, key) }
    catch { screen.set('config'); return }

    // Check existing session
    const { data: { session } } = await sb.auth.getSession()
    if (!session) { screen.set('signin'); return }

    user.set(session.user)
    await loadAll(sb)
    screen.set('main')
  })

  async function loadAll(sb) {
    loading.set(true)
    try {
      const { data: logData, error: logErr } = await sb
        .from('work_logs').select('*').order('timestamp', { ascending: true })
      if (logErr) throw logErr
      logs.set(logData || [])

      const { data: settingData } = await sb
        .from('work_settings').select('value').eq('key', 'requiredDailyHours').single()
      if (settingData) requiredHours.set(parseFloat(settingData.value) || 9)
      else requiredHours.set(parseFloat(localStorage.getItem('whl_req_hours') || '9'))
    } catch (e) {
      console.error('loadAll error', e)
    } finally {
      loading.set(false)
    }
  }

  $: isApp = ['main', 'logs', 'settings'].includes($screen)
</script>

<Spinner />
<Toast />

{#if $screen === 'loading'}
  <!-- intentionally blank — Spinner overlay is shown -->
{:else if $screen === 'config'}
  <ConfigScreen />
{:else if $screen === 'signin'}
  <SignInScreen />
{:else if isApp}
  <TopBar />
  <div class="app-body">
    {#if $screen === 'main'}
      <MainScreen />
    {:else if $screen === 'logs'}
      <LogsScreen />
    {:else if $screen === 'settings'}
      <SettingsScreen />
    {/if}
  </div>
{/if}

<style>
  .app-body {
    min-height: calc(100dvh - 56px);
  }
</style>
