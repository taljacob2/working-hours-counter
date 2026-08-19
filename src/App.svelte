<script>
  import { onMount, onDestroy } from 'svelte'
  import { screen, user, logs, requiredHours, minimumDailyHours, maximumDailyHours, commuteGapMinutes, use24HourFormat, loading, theme, offDays, dayOverrides, officeLocations, activeOfficeId, officeLocation, autoTrackEnabled, showToast, rebalHistoryCap, notifMorningEnabled, notifMorningTime, notifEveningEnabled, notifEveningTime, notifTargetEnabled, notifTargetHoursOverride, notifDeliverVia, excelColorHomeHours, fillMissingOfficeHours, companyName, employeeName, employeeCode, cardNumber, payrollNumber, employmentStartDate, workAgreementText } from './stores/appStore.js'
  import { initSupabase, getSupabase } from './lib/supabase.js'
  import { GeoFenceWatcher } from './lib/geoFence.js'
  import { dateKey } from './lib/timeUtils.js'
  import { rescheduleAll, cancelTodayReminders, scheduleTargetReached, cancelTargetReached, requestNotificationPermission } from './lib/notifications.js'

  import Spinner     from './components/Spinner.svelte'
  import Toast       from './components/Toast.svelte'
  import InstallBanner from './components/InstallBanner.svelte'
  import TopBar      from './components/TopBar.svelte'
  import ConfigScreen   from './screens/ConfigScreen.svelte'
  import SignInScreen   from './screens/SignInScreen.svelte'
  import MainScreen     from './screens/MainScreen.svelte'
  import LogsScreen     from './screens/LogsScreen.svelte'
  import SettingsScreen   from './screens/SettingsScreen.svelte'
  import AnalyticsScreen  from './screens/AnalyticsScreen.svelte'

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
    scheduleNotifications()
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
      enterThresholdMs: (loc.resumeThresholdHours ?? 0.25) * 3_600_000,
      leaveThresholdMs: (loc.pauseThresholdHours  ?? 0.25) * 3_600_000,
      fireOnInitialInside: true,
      onEnter: crossedAt => pressOffice('resume', crossedAt),
      onLeave: crossedAt => pressOffice('pause',  crossedAt),
    })
    geoWatcher.start()
  }

  function stopGeoFence() {
    geoWatcher?.stop()
    geoWatcher = null
  }

  // Re-start whenever settings change
  $: if ($autoTrackEnabled !== undefined || $officeLocation !== undefined) startGeoFence()

  // ── Notifications ────────────────────────────────────────────
  let notifReady = false

  async function scheduleNotifications() {
    notifReady = true
    // Settings can say "on" (e.g. synced from another device) without this
    // device ever having actually granted the OS permission — verify/request
    // it here too, not just from the Settings toggle, so a silent permission
    // gap doesn't just fail every scheduled notification with no feedback.
    if (($notifMorningEnabled || $notifEveningEnabled || $notifTargetEnabled) && $notifDeliverVia !== 'push') {
      const granted = await requestNotificationPermission()
      if (!granted) showToast('Notification permission not granted — reminders won\'t fire. Enable it in system settings.', 'error')
    }
    rescheduleAll({
      morningEnabled: $notifMorningEnabled,
      morningTime:    $notifMorningTime,
      eveningEnabled: $notifEveningEnabled,
      eveningTime:    $notifEveningTime,
      offDaysArr:     $offDays,
      dayOverridesObj: $dayOverrides,
      deliverVia:     $notifDeliverVia,
    })
  }

  $: if (notifReady) scheduleNotifications(
    $notifMorningEnabled, $notifMorningTime,
    $notifEveningEnabled, $notifEveningTime,
    $offDays, $dayOverrides, $notifDeliverVia
  )

  onDestroy(stopGeoFence)

  async function pressOffice(action, crossedAt = new Date()) {
    const sb = getSupabase()
    const dk = dateKey(crossedAt)
    const { data: dayLogs } = await sb.from('work_logs')
      .select('*').eq('date_key', dk).eq('platform', 'office')
      .order('timestamp', { ascending: false }).limit(1)
    const last = dayLogs?.[0]
    if (last?.action === action) return  // already in this state — idempotent
    const entry = {
      id: crypto.randomUUID(),
      platform: 'office',
      action,
      timestamp: crossedAt.toISOString(),
      date_key: dk,
      created_at: new Date().toISOString(),
      note: '',
    }
    const { error } = await sb.from('work_logs').insert(entry)
    if (error) { showToast('Auto-track save failed: ' + error.message, 'error'); return }
    logs.update(l => [...l, entry])
    showToast(`🏢 Auto-tracked: office ${action}d`, 'success')
    if (action === 'resume') {
      cancelTodayReminders()
      if ($notifTargetEnabled) scheduleTargetReached(crossedAt, ($notifTargetHoursOverride ?? $requiredHours) * 3_600_000)
    } else {
      cancelTargetReached()
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
      const offDaysRaw = offDaysVal ?? offDaysLocal ?? '[5,6]'
      try { offDays.set(JSON.parse(offDaysRaw)) } catch { offDays.set([5, 6]) }

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

      const rebalCapVal = settings?.find(s => s.key === 'rebalHistoryCap')?.value
      rebalHistoryCap.set(parseInt(rebalCapVal ?? localStorage.getItem('whl_rebal_history_cap') ?? '0', 10))

      const nme = settings?.find(s => s.key === 'notifMorningEnabled')?.value
      notifMorningEnabled.set((nme ?? localStorage.getItem('whl_notif_morning') ?? 'false') === 'true')
      const nmt = settings?.find(s => s.key === 'notifMorningTime')?.value
      notifMorningTime.set(nmt ?? localStorage.getItem('whl_notif_morning_time') ?? '09:00')
      const nee = settings?.find(s => s.key === 'notifEveningEnabled')?.value
      notifEveningEnabled.set((nee ?? localStorage.getItem('whl_notif_evening') ?? 'false') === 'true')
      const net = settings?.find(s => s.key === 'notifEveningTime')?.value
      notifEveningTime.set(net ?? localStorage.getItem('whl_notif_evening_time') ?? '19:00')
      const nte = settings?.find(s => s.key === 'notifTargetEnabled')?.value
      notifTargetEnabled.set((nte ?? localStorage.getItem('whl_notif_target') ?? 'false') === 'true')
      const ntho = settings?.find(s => s.key === 'notifTargetHoursOverride')?.value
      const nthoLocal = localStorage.getItem('whl_notif_target_hours')
      const nthoRaw = ntho ?? nthoLocal ?? ''
      notifTargetHoursOverride.set(nthoRaw && nthoRaw !== '' ? parseFloat(nthoRaw) : null)
      const ndv = settings?.find(s => s.key === 'notifDeliverVia')?.value
      notifDeliverVia.set(ndv ?? localStorage.getItem('whl_notif_deliver_via') ?? 'both')

      const echh = settings?.find(s => s.key === 'excelColorHomeHours')?.value
      excelColorHomeHours.set((echh ?? localStorage.getItem('whl_excel_color_home') ?? 'false') === 'true')

      const fmoh = settings?.find(s => s.key === 'fillMissingOfficeHours')?.value
      fillMissingOfficeHours.set((fmoh ?? localStorage.getItem('whl_fill_missing_office') ?? 'true') === 'true')

      const cn = settings?.find(s => s.key === 'companyName')?.value
      companyName.set(cn ?? localStorage.getItem('whl_company_name') ?? '')
      const en = settings?.find(s => s.key === 'employeeName')?.value
      employeeName.set(en ?? localStorage.getItem('whl_employee_name') ?? '')
      const ec = settings?.find(s => s.key === 'employeeCode')?.value
      employeeCode.set(ec ?? localStorage.getItem('whl_employee_code') ?? '')
      const ccn = settings?.find(s => s.key === 'cardNumber')?.value
      cardNumber.set(ccn ?? localStorage.getItem('whl_card_number') ?? '')
      const pn = settings?.find(s => s.key === 'payrollNumber')?.value
      payrollNumber.set(pn ?? localStorage.getItem('whl_payroll_number') ?? '')
      const sd = settings?.find(s => s.key === 'employmentStartDate')?.value
      employmentStartDate.set(sd ?? localStorage.getItem('whl_employment_start_date') ?? '')
      const at = settings?.find(s => s.key === 'workAgreementText')?.value
      workAgreementText.set(at ?? localStorage.getItem('whl_work_agreement_text') ?? '')
    } catch (e) {
      console.error('loadAll error', e)
    } finally {
      loading.set(false)
    }
  }

  $: isApp = ['main', 'logs', 'analytics', 'settings'].includes($screen)
</script>

<Spinner />
<Toast />
{#if $screen !== 'loading'}
  <InstallBanner />
{/if}

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
    {:else if $screen === 'analytics'}
      <AnalyticsScreen />
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
