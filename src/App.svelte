<script>
  import { onMount, onDestroy } from 'svelte'
  import { screen, user, logs, requiredHours, minimumDailyHours, maximumDailyHours, commuteGapMinutes, use24HourFormat, loading, theme, offDays, dayOverrides, officeLocations, activeOfficeId, officeLocation, autoTrackEnabled, showToast } from './stores/appStore.js'
  import { initSupabase, getSupabase } from './lib/supabase.js'
  import { GeoFenceWatcher } from './lib/geoFence.js'
  import { dateKey } from './lib/timeUtils.js'

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
    startGeoFence()
  })

  // ── GeoFence watcher ─────────────────────────────────────────
  let geoWatcher = null

  function startGeoFence() {
    stopGeoFence()
    const loc = $officeLocation
    const enabled = $autoTrackEnabled
    if (!enabled || !loc) return

    geoWatcher = new GeoFenceWatcher({
      location: loc,
      onEnter: () => pressOffice('resume'),
      onLeave: () => pressOffice('pause'),
    })
    geoWatcher.start()
  }

  function stopGeoFence() {
    geoWatcher?.stop()
    geoWatcher = null
  }

  // Re-start whenever settings change
  $: if ($autoTrackEnabled !== undefined || $officeLocation !== undefined) startGeoFence()

  onDestroy(stopGeoFence)

  async function pressOffice(action) {
    const sb = getSupabase()
    const today = dateKey()
    const { data: todayLogs } = await sb.from('work_logs')
      .select('*').eq('date_key', today).eq('platform', 'office')
      .order('timestamp', { ascending: false }).limit(1)
    const last = todayLogs?.[0]
    if (last?.action === action) return  // already in this state — idempotent
    const entry = {
      id: crypto.randomUUID(),
      platform: 'office',
      action,
      timestamp: new Date().toISOString(),
      date_key: today,
      created_at: new Date().toISOString(),
      note: '',
    }
    const { error } = await sb.from('work_logs').insert(entry)
    if (error) { showToast('Auto-track save failed: ' + error.message, 'error'); return }
    logs.update(l => [...l, entry])
    showToast(`🏢 Auto-tracked: office ${action}d`, 'success')
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

      const dayOverridesVal = settings?.find(s => s.key === 'dayOverrides')?.value
      const dayOverridesLocal = localStorage.getItem('whl_day_overrides')
      const dayOverridesRaw = dayOverridesVal ?? dayOverridesLocal ?? '{}'
      try { dayOverrides.set(JSON.parse(dayOverridesRaw)) } catch { dayOverrides.set({}) }

      const officeLocsVal = settings?.find(s => s.key === 'officeLocations')?.value
      const officeLocsLocal = localStorage.getItem('whl_office_locations')
      if (officeLocsVal || officeLocsLocal) {
        try { officeLocations.set(JSON.parse(officeLocsVal ?? officeLocsLocal)) } catch { officeLocations.set([]) }
        const activeIdVal = settings?.find(s => s.key === 'activeOfficeId')?.value
        const activeIdLocal = localStorage.getItem('whl_active_office_id')
        activeOfficeId.set(activeIdVal || activeIdLocal || null)
      } else {
        // Migrate from old single-location format
        const oldLocVal = settings?.find(s => s.key === 'officeLocation')?.value
        const oldLocLocal = localStorage.getItem('whl_office_location')
        const oldLocRaw = oldLocVal ?? oldLocLocal ?? 'null'
        try {
          const oldLoc = JSON.parse(oldLocRaw)
          if (oldLoc) {
            const id = crypto.randomUUID()
            const migrated = [{ id, name: 'Office', ...oldLoc }]
            officeLocations.set(migrated)
            activeOfficeId.set(id)
          }
        } catch { officeLocations.set([]) }
      }

      const autoTrackVal = settings?.find(s => s.key === 'autoTrackEnabled')?.value
      const autoTrackLocal = localStorage.getItem('whl_auto_track')
      autoTrackEnabled.set((autoTrackVal ?? autoTrackLocal) === 'true')
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
