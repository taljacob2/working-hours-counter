<script>
  import { onMount } from 'svelte'
  import { screen, user, logs, requiredHours, minimumDailyHours, maximumDailyHours, use24HourFormat, loading, theme, offDays } from './stores/appStore.js'
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

    // Check Supabase config (Env vars first, then localStorage)
    const url = import.meta.env.NEXT_PUBLIC_SUPABASE_URL || localStorage.getItem('whl_sb_url')
    const key = import.meta.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || localStorage.getItem('whl_sb_key')
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

      const { data: settings } = await sb.from('work_settings').select('key, value')
      const reqVal = settings?.find(s => s.key === 'requiredDailyHours')?.value
      const minVal = settings?.find(s => s.key === 'minimumDailyHours')?.value
      const maxVal = settings?.find(s => s.key === 'maximumDailyHours')?.value
      const gapVal = settings?.find(s => s.key === 'commuteGapMinutes')?.value
      const use24Val = settings?.find(s => s.key === 'use24HourFormat')?.value

      requiredHours.set(parseFloat(reqVal ?? localStorage.getItem('whl_req_hours') ?? '9'))
      minimumDailyHours.set(parseFloat(minVal ?? localStorage.getItem('whl_min_hours') ?? '5'))
      maximumDailyHours.set(parseFloat(maxVal ?? localStorage.getItem('whl_max_hours') ?? '12'))
      commuteGapMinutes.set(parseInt(gapVal ?? localStorage.getItem('whl_commute_gap') ?? '45', 10))
      
      const local24 = localStorage.getItem('whl_24h_format')
      use24HourFormat.set(use24Val ? use24Val === 'true' : (local24 ? local24 === 'true' : true))

      const offDaysVal = settings?.find(s => s.key === 'offDays')?.value
      const offDaysLocal = localStorage.getItem('whl_off_days')
      const offDaysRaw = offDaysVal ?? offDaysLocal ?? '[0,6]'
      try { offDays.set(JSON.parse(offDaysRaw)) } catch { offDays.set([0, 6]) }
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
  @media (max-width: 600px) {
    .app-body {
      padding-bottom: calc(4.5rem + env(safe-area-inset-bottom));
    }
  }
</style>
