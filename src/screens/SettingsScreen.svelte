<script>
  import { onMount, onDestroy } from 'svelte'
  import { requiredHours, minimumDailyHours, maximumDailyHours, commuteGapMinutes, use24HourFormat, offDays, dayOverrides, logs, screen, user, showToast, loading, officeLocations, activeOfficeId, autoTrackEnabled, rebalHistoryCap, notifMorningEnabled, notifMorningTime, notifEveningEnabled, notifEveningTime, notifTargetEnabled, notifTargetHoursOverride } from '../stores/appStore.js'
  import { requestNotificationPermission } from '../lib/notifications.js'
  import { getSupabase } from '../lib/supabase.js'
  import { exportCsv, saveFile } from '../lib/exportUtils.js'
  import { monthBounds } from '../lib/timeUtils.js'

  let reqHoursLocal = 9
  requiredHours.subscribe(v => reqHoursLocal = v)

  let minHoursLocal = 5
  minimumDailyHours.subscribe(v => minHoursLocal = v)

  let maxHoursLocal = 12
  maximumDailyHours.subscribe(v => maxHoursLocal = v)

  let commuteGapLocal = 45
  commuteGapMinutes.subscribe(v => commuteGapLocal = v)

  let rebalHistoryCapLocal = 0
  rebalHistoryCap.subscribe(v => rebalHistoryCapLocal = v)

  let notifMorningEnabledLocal = false
  notifMorningEnabled.subscribe(v => notifMorningEnabledLocal = v)
  let notifMorningTimeLocal = '09:00'
  notifMorningTime.subscribe(v => notifMorningTimeLocal = v)
  let notifEveningEnabledLocal = false
  notifEveningEnabled.subscribe(v => notifEveningEnabledLocal = v)
  let notifEveningTimeLocal = '19:00'
  notifEveningTime.subscribe(v => notifEveningTimeLocal = v)
  let notifTargetEnabledLocal = false
  notifTargetEnabled.subscribe(v => notifTargetEnabledLocal = v)
  let notifTargetHoursLocal = null
  notifTargetHoursOverride.subscribe(v => notifTargetHoursLocal = v)

  async function toggleNotif(store, localSetter, newValue) {
    if (newValue) {
      const granted = await requestNotificationPermission()
      if (!granted) { showToast('Notification permission denied', 'error'); return }
    }
    localSetter(newValue)
  }

  let use24Local = true
  use24HourFormat.subscribe(v => use24Local = v)

  const DAY_OPTIONS = [['Sun', 0], ['Mon', 1], ['Tue', 2], ['Wed', 3], ['Thu', 4], ['Fri', 5], ['Sat', 6]]
  let offDaysLocal = [0, 6]
  offDays.subscribe(v => offDaysLocal = [...v])

  function toggleOffDay(idx, checked) {
    if (checked) offDaysLocal = [...offDaysLocal, idx].sort((a, b) => a - b)
    else offDaysLocal = offDaysLocal.filter(d => d !== idx)
  }

  // Sync slider ↔ number input
  function onReqSlider(e)  { reqHoursLocal = parseFloat(e.target.value) }
  function onReqNumber(e)  { reqHoursLocal = Math.min(14, Math.max(4, parseFloat(e.target.value) || 9)) }

  function onMinSlider(e)  { minHoursLocal = parseFloat(e.target.value) }
  function onMinNumber(e)  { minHoursLocal = Math.min(14, Math.max(1, parseFloat(e.target.value) || 5)) }

  function onMaxSlider(e)  { maxHoursLocal = parseFloat(e.target.value) }
  function onMaxNumber(e)  { maxHoursLocal = Math.min(24, Math.max(8, parseFloat(e.target.value) || 12)) }

  function onGapSlider(e)  { commuteGapLocal = parseInt(e.target.value) }
  function onGapNumber(e)  { commuteGapLocal = Math.min(180, Math.max(0, parseInt(e.target.value) || 45)) }

  async function saveSettings() {
    requiredHours.set(reqHoursLocal)
    localStorage.setItem('whl_req_hours', String(reqHoursLocal))

    minimumDailyHours.set(minHoursLocal)
    localStorage.setItem('whl_min_hours', String(minHoursLocal))

    maximumDailyHours.set(maxHoursLocal)
    localStorage.setItem('whl_max_hours', String(maxHoursLocal))

    use24HourFormat.set(use24Local)
    localStorage.setItem('whl_24h_format', String(use24Local))

    commuteGapMinutes.set(commuteGapLocal)
    localStorage.setItem('whl_commute_gap', String(commuteGapLocal))

    rebalHistoryCap.set(rebalHistoryCapLocal)
    localStorage.setItem('whl_rebal_history_cap', String(rebalHistoryCapLocal))

    // If the off-days configuration changed, clear all per-date overrides — they were
    // set relative to the old config and would silently shadow the new one.
    const offDaysChanged = [...$offDays].sort().join(',') !== [...offDaysLocal].sort().join(',')
    offDays.set([...offDaysLocal])
    localStorage.setItem('whl_off_days', JSON.stringify(offDaysLocal))
    if (offDaysChanged) {
      dayOverrides.set({})
      localStorage.setItem('whl_day_overrides', '{}')
    }

    const sb = getSupabase()
    notifMorningEnabled.set(notifMorningEnabledLocal)
    localStorage.setItem('whl_notif_morning', String(notifMorningEnabledLocal))
    notifMorningTime.set(notifMorningTimeLocal)
    localStorage.setItem('whl_notif_morning_time', notifMorningTimeLocal)
    notifEveningEnabled.set(notifEveningEnabledLocal)
    localStorage.setItem('whl_notif_evening', String(notifEveningEnabledLocal))
    notifEveningTime.set(notifEveningTimeLocal)
    localStorage.setItem('whl_notif_evening_time', notifEveningTimeLocal)
    notifTargetEnabled.set(notifTargetEnabledLocal)
    localStorage.setItem('whl_notif_target', String(notifTargetEnabledLocal))
    notifTargetHoursOverride.set(notifTargetHoursLocal)
    localStorage.setItem('whl_notif_target_hours', notifTargetHoursLocal != null ? String(notifTargetHoursLocal) : '')

    const upsertRows = [
      { key: 'requiredDailyHours', value: String(reqHoursLocal) },
      { key: 'minimumDailyHours', value: String(minHoursLocal) },
      { key: 'maximumDailyHours', value: String(maxHoursLocal) },
      { key: 'commuteGapMinutes', value: String(commuteGapLocal) },
      { key: 'use24HourFormat', value: String(use24Local) },
      { key: 'offDays', value: JSON.stringify(offDaysLocal) },
      { key: 'rebalHistoryCap', value: String(rebalHistoryCapLocal) },
      { key: 'notifMorningEnabled', value: String(notifMorningEnabledLocal) },
      { key: 'notifMorningTime',    value: notifMorningTimeLocal },
      { key: 'notifEveningEnabled', value: String(notifEveningEnabledLocal) },
      { key: 'notifEveningTime',    value: notifEveningTimeLocal },
      { key: 'notifTargetEnabled',  value: String(notifTargetEnabledLocal) },
      { key: 'notifTargetHoursOverride', value: notifTargetHoursLocal != null ? String(notifTargetHoursLocal) : '' },
    ]
    if (offDaysChanged) upsertRows.push({ key: 'dayOverrides', value: '{}' })
    const { error } = await sb.from('work_settings').upsert(upsertRows)
    if (error) showToast('Settings save failed: ' + error.message, 'error')
    else showToast('Settings saved ✓', 'success')
  }

  // ── Export ───────────────────────────────────────────────────
  const currentYear  = new Date().getFullYear()
  const currentMonth = new Date().getMonth() + 1
  let expYear     = currentYear
  let expMonth    = currentMonth
  let expPlatform = 'all'   // 'all' | 'home' | 'office'
  let expCompact  = false
  let expHebrew   = false
  let expCount    = null

  const years  = Array.from({ length: 5 }, (_, i) => currentYear - i)
  const months = [
    [1,'January'],[2,'February'],[3,'March'],[4,'April'],
    [5,'May'],[6,'June'],[7,'July'],[8,'August'],
    [9,'September'],[10,'October'],[11,'November'],[12,'December'],
  ]

  $: {
    const { start, end } = monthBounds(expYear, expMonth)
    expCount = $logs.filter(l =>
      l.date_key >= start && l.date_key <= end &&
      (expPlatform === 'all' || l.platform === expPlatform)
    ).length
  }

  function _expSubset() {
    const { start, end } = monthBounds(expYear, expMonth)
    return $logs.filter(l =>
      l.date_key >= start && l.date_key <= end &&
      (expPlatform === 'all' || l.platform === expPlatform)
    )
  }

  function _expFileStem() {
    const mo = `${expYear}-${String(expMonth).padStart(2,'0')}`
    const platSuffix    = expPlatform !== 'all' ? `-${expPlatform}` : ''
    const compactSuffix = expCompact  ? '-compact' : ''
    const heSuffix      = expHebrew   ? '-he' : ''
    return `work-logs-${mo}${platSuffix}${compactSuffix}${heSuffix}`
  }

  async function doExport() {
    const subset = _expSubset()
    if (!subset.length) { showToast('No logs for that month', 'info'); return }
    try {
      await exportCsv(subset, `${_expFileStem()}.csv`, use24Local, expCompact, expHebrew)
      showToast(`Exported ${subset.length} records`, 'success')
    } catch (e) {
      if (e?.message !== 'cancelled') showToast('Export failed', 'error')
    }
  }

  async function doExportJson() {
    const subset = _expSubset()
    if (!subset.length) { showToast('No logs for that month', 'info'); return }
    const { start, end } = monthBounds(expYear, expMonth)
    const monthDayOverrides = Object.fromEntries(
      Object.entries($dayOverrides).filter(([dk]) => dk >= start && dk <= end)
    )
    const payload = {
      exported_at: new Date().toISOString(),
      month: `${expYear}-${String(expMonth).padStart(2,'0')}`,
      ...(expPlatform !== 'all' ? { platform_filter: expPlatform } : {}),
      day_schedule: monthDayOverrides,
      logs: subset,
    }
    try {
      await saveFile(JSON.stringify(payload, null, 2), `${_expFileStem()}.json`, 'application/json')
      showToast(`Exported ${subset.length} records as JSON`, 'success')
    } catch (e) {
      if (e?.message !== 'cancelled') showToast('Export failed', 'error')
    }
  }

  // ── Import ────────────────────────────────────────────────────
  let importFileInput
  let importFile = null
  let importing = false

  function parseImportFile(text) {
    const parsed = JSON.parse(text)
    const importLogs = Array.isArray(parsed) ? parsed : parsed.logs
    if (!importLogs?.length) { showToast('No logs found in file', 'error'); return null }
    const required = ['id', 'timestamp', 'platform', 'action', 'date_key']
    if (!importLogs.every(l => required.every(f => l[f] != null))) {
      showToast('Invalid log format — missing required fields', 'error'); return null
    }
    const importDayOverrides = (parsed.day_schedule && typeof parsed.day_schedule === 'object' && !Array.isArray(parsed.day_schedule))
      ? parsed.day_schedule
      : {}
    return { logs: importLogs, dayOverrides: importDayOverrides }
  }

  async function doImportMerge() {
    if (!importFile) return
    importing = true
    try {
      const parsed = parseImportFile(await importFile.text())
      if (!parsed) return
      const { logs: importLogs, dayOverrides: importDayOverrides } = parsed
      const sb = getSupabase()
      const { error } = await sb.from('work_logs').upsert(importLogs, { onConflict: 'id' })
      if (error) { showToast('Import failed: ' + error.message, 'error'); return }
      logs.update(ls => {
        const importIds = new Set(importLogs.map(l => l.id))
        return [...ls.filter(l => !importIds.has(l.id)), ...importLogs]
      })
      if (Object.keys(importDayOverrides).length) {
        const merged = { ...$dayOverrides, ...importDayOverrides }
        dayOverrides.set(merged)
        localStorage.setItem('whl_day_overrides', JSON.stringify(merged))
        await sb.from('work_settings').upsert([{ key: 'dayOverrides', value: JSON.stringify(merged) }])
      }
      showToast(`Merged ${importLogs.length} records`, 'success')
      importFile = null
      if (importFileInput) importFileInput.value = ''
    } catch (e) {
      showToast('Import failed: ' + e.message, 'error')
    } finally {
      importing = false
    }
  }

  async function doImportReplace() {
    if (!importFile) return
    importing = true
    try {
      const parsed = parseImportFile(await importFile.text())
      if (!parsed) return
      const { logs: importLogs, dayOverrides: importDayOverrides } = parsed
      const months = [...new Set(importLogs.map(l => l.date_key.slice(0, 7)))]
      const sb = getSupabase()
      for (const month of months) {
        const { error } = await sb.from('work_logs')
          .delete().gte('date_key', `${month}-01`).lte('date_key', `${month}-31`)
        if (error) { showToast('Replace failed: ' + error.message, 'error'); return }
      }
      const { error } = await sb.from('work_logs').insert(importLogs)
      if (error) { showToast('Replace failed: ' + error.message, 'error'); return }
      const monthSet = new Set(months)
      logs.update(ls => [...ls.filter(l => !monthSet.has(l.date_key.slice(0, 7))), ...importLogs])
      // Drop overrides belonging to the replaced months, then apply imported ones
      const updatedOverrides = Object.fromEntries(
        Object.entries($dayOverrides).filter(([dk]) => !monthSet.has(dk.slice(0, 7)))
      )
      Object.assign(updatedOverrides, importDayOverrides)
      dayOverrides.set(updatedOverrides)
      localStorage.setItem('whl_day_overrides', JSON.stringify(updatedOverrides))
      await sb.from('work_settings').upsert([{ key: 'dayOverrides', value: JSON.stringify(updatedOverrides) }])
      showToast(`Replaced ${months.join(', ')} — ${importLogs.length} records`, 'success')
      importFile = null
      if (importFileInput) importFileInput.value = ''
    } catch (e) {
      showToast('Import failed: ' + e.message, 'error')
    } finally {
      importing = false
    }
  }

  // ── Office Location / Auto-Track ─────────────────────────────
  let officeLocsLocal = []
  officeLocations.subscribe(v => officeLocsLocal = v)

  let activeOfficeIdLocal = null
  activeOfficeId.subscribe(v => activeOfficeIdLocal = v)

  let autoTrackLocal = false
  autoTrackEnabled.subscribe(v => autoTrackLocal = v)

  let officeRadiusLocal = 200
  let resumeThresholdLocal = 2
  let pauseThresholdLocal = 2
  $: activeLocLocal = officeLocsLocal.find(l => l.id === activeOfficeIdLocal) ?? null
  $: if (activeLocLocal) {
    officeRadiusLocal = activeLocLocal.radiusMeters
    resumeThresholdLocal = activeLocLocal.resumeThresholdHours ?? 2
    pauseThresholdLocal  = activeLocLocal.pauseThresholdHours  ?? 2
  }

  let newLocName = ''
  let addingLocation = false

  async function captureAndAdd() {
    if (!navigator?.geolocation) { showToast('Geolocation not available', 'error'); return }
    addingLocation = true
    navigator.geolocation.getCurrentPosition(
      async pos => {
        addingLocation = false
        const id = crypto.randomUUID()
        const name = newLocName.trim() || 'Office'
        const loc = { id, name, lat: pos.coords.latitude, lng: pos.coords.longitude, radiusMeters: 200, resumeThresholdHours: 2, pauseThresholdHours: 2 }
        newLocName = ''
        await saveLocations([...officeLocsLocal, loc], id, true)
        showToast(`Added "${loc.name}"`, 'success')
      },
      err => { addingLocation = false; showToast('Could not get location: ' + err.message, 'error') },
      { enableHighAccuracy: true, timeout: 10_000 }
    )
  }

  async function setActive(id) {
    const name = officeLocsLocal.find(l => l.id === id)?.name ?? 'location'
    await saveLocations(officeLocsLocal, id, true)
    showToast(`Switched to "${name}"`, 'success')
  }

  async function updateActiveRadius() {
    if (!activeLocLocal) return
    const updated = officeLocsLocal.map(l => l.id === activeOfficeIdLocal ? { ...l, radiusMeters: officeRadiusLocal } : l)
    await saveLocations(updated, activeOfficeIdLocal, false)
  }

  async function updateThresholds() {
    if (!activeLocLocal) return
    const updated = officeLocsLocal.map(l => l.id === activeOfficeIdLocal
      ? { ...l, resumeThresholdHours: resumeThresholdLocal, pauseThresholdHours: pauseThresholdLocal }
      : l)
    await saveLocations(updated, activeOfficeIdLocal, false)
  }

  async function updateActiveGPS() {
    if (!navigator?.geolocation || !activeLocLocal) return
    addingLocation = true
    navigator.geolocation.getCurrentPosition(
      async pos => {
        addingLocation = false
        const updated = officeLocsLocal.map(l => l.id === activeOfficeIdLocal
          ? { ...l, lat: pos.coords.latitude, lng: pos.coords.longitude }
          : l)
        await saveLocations(updated, activeOfficeIdLocal, false)
        showToast('GPS position updated ✓', 'success')
      },
      err => { addingLocation = false; showToast('Could not get location: ' + err.message, 'error') },
      { enableHighAccuracy: true, timeout: 10_000 }
    )
  }

  async function renameLocation(id, name) {
    const trimmed = name.trim() || 'Office'
    if (officeLocsLocal.find(l => l.id === id)?.name === trimmed) return
    const updated = officeLocsLocal.map(l => l.id === id ? { ...l, name: trimmed } : l)
    await saveLocations(updated, activeOfficeIdLocal, false)
  }

  async function deleteLocation(id) {
    const updated = officeLocsLocal.filter(l => l.id !== id)
    const wasActive = activeOfficeIdLocal === id
    const newActiveId = wasActive ? (updated[0]?.id ?? null) : activeOfficeIdLocal
    await saveLocations(updated, newActiveId, false)
    if (wasActive && !newActiveId) {
      autoTrackLocal = false
      autoTrackEnabled.set(false)
      localStorage.setItem('whl_auto_track', 'false')
      const sb = getSupabase()
      await sb.from('work_settings').upsert([{ key: 'autoTrackEnabled', value: 'false' }])
    }
    showToast('Location removed', 'info')
  }

  async function saveLocations(locs, activeId, autoEnable) {
    officeLocations.set(locs)
    activeOfficeId.set(activeId)
    activeOfficeIdLocal = activeId
    localStorage.setItem('whl_office_locations', JSON.stringify(locs))
    localStorage.setItem('whl_active_office_id', activeId ?? '')
    const upsertRows = [
      { key: 'officeLocations', value: JSON.stringify(locs) },
      { key: 'activeOfficeId', value: activeId ?? '' },
    ]
    if (autoEnable && !autoTrackLocal) {
      autoTrackLocal = true
      autoTrackEnabled.set(true)
      localStorage.setItem('whl_auto_track', 'true')
      upsertRows.push({ key: 'autoTrackEnabled', value: 'true' })
    }
    const sb = getSupabase()
    const { error } = await sb.from('work_settings').upsert(upsertRows)
    if (error) showToast('Failed to save', 'error')
  }

  async function toggleAutoTrack() {
    autoTrackLocal = !autoTrackLocal
    autoTrackEnabled.set(autoTrackLocal)
    localStorage.setItem('whl_auto_track', String(autoTrackLocal))
    const sb = getSupabase()
    await sb.from('work_settings').upsert([{ key: 'autoTrackEnabled', value: String(autoTrackLocal) }])
    showToast(autoTrackLocal ? 'Auto-track enabled' : 'Auto-track disabled', 'info')
  }

  // ── Live distance from office center ─────────────────────────
  let liveDistance = null  // metres, null = no fix yet
  let liveWatchId = null

  function _geodist(lat1, lng1, lat2, lng2) {
    const R = 6_371_000, toRad = d => d * Math.PI / 180
    const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1)
    const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng/2)**2
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a))
  }

  onMount(() => {
    if (!navigator?.geolocation) return
    liveWatchId = navigator.geolocation.watchPosition(
      pos => {
        if (!activeLocLocal) { liveDistance = null; return }
        liveDistance = Math.round(_geodist(pos.coords.latitude, pos.coords.longitude, activeLocLocal.lat, activeLocLocal.lng))
      },
      () => {},
      { enableHighAccuracy: true, maximumAge: 5_000 }
    )
  })

  onDestroy(() => {
    if (liveWatchId !== null) navigator.geolocation.clearWatch(liveWatchId)
  })

  $: liveInside = liveDistance !== null && activeLocLocal ? liveDistance <= activeLocLocal.radiusMeters : null

  // ── Auth / Reconfig ──────────────────────────────────────────
  async function signOut() {
    const sb = getSupabase()
    await sb.auth.signOut()
    user.set(null)
    screen.set('signin')
    showToast('Signed out', 'info')
  }

  function reconfigure() {
    if (import.meta.env.NEXT_PUBLIC_SUPABASE_URL) {
      showToast('Config is locked to Environment Variables', 'info')
      return
    }
    localStorage.removeItem('whl_sb_url')
    localStorage.removeItem('whl_sb_key')
    screen.set('config')
  }

  const maskedUrl = (() => {
    const raw = import.meta.env.NEXT_PUBLIC_SUPABASE_URL || localStorage.getItem('whl_sb_url') || ''
    return raw.length > 30 ? raw.slice(0, 20) + '…' + raw.slice(-10) : raw
  })()
</script>

<div class="settings-screen">
  <h1 class="page-title">Settings</h1>

  <!-- Preferences -->
  <div class="card">
    <p class="section-title">Preferences</p>
    
    <div style="margin-bottom: 1.5rem">
      <label>Required Daily Hours</label>
      <div class="hours-row" style="margin-top: 0.25rem">
        <input id="req-slider" type="range" min="4" max="14" step="0.5"
          bind:value={reqHoursLocal} on:input={onReqSlider}
          style="flex:1"
        />
        <input id="req-num" type="number" min="4" max="14" step="0.5"
          bind:value={reqHoursLocal} on:input={onReqNumber}
          style="width:80px"
        />
        <span class="hours-label">h / day</span>
      </div>
      <p class="info-text" style="margin-top: 0.5rem; font-size: 0.8rem">
        The daily target. Days that fall short of this are marked as negative overtime.
      </p>
    </div>

    <div style="margin-bottom: 1.5rem">
      <label>Minimum Daily Hours</label>
      <div class="hours-row" style="margin-top: 0.25rem">
        <input id="min-slider" type="range" min="1" max="14" step="0.5"
          bind:value={minHoursLocal} on:input={onMinSlider}
          style="flex:1"
        />
        <input id="min-num" type="number" min="1" max="14" step="0.5"
          bind:value={minHoursLocal} on:input={onMinNumber}
          style="width:80px"
        />
        <span class="hours-label">h / day</span>
      </div>
      <p class="info-text" style="margin-top: 0.5rem; font-size: 0.8rem">
        The lower bound. Days where you log time but fall short of this are flagged with a warning.
      </p>
    </div>

    <div style="margin-bottom: 1.5rem">
      <label>Maximum Daily Hours</label>
      <div class="hours-row" style="margin-top: 0.25rem">
        <input id="max-slider" type="range" min="8" max="24" step="0.5"
          bind:value={maxHoursLocal} on:input={onMaxSlider}
          style="flex:1"
        />
        <input id="max-num" type="number" min="8" max="24" step="0.5"
          bind:value={maxHoursLocal} on:input={onMaxNumber}
          style="width:80px"
        />
        <span class="hours-label">h / day</span>
      </div>
      <p class="info-text" style="margin-top: 0.5rem; font-size: 0.8rem">
        The upper bound. Days where you exceed this are highlighted in the calendar and can be filtered.
      </p>
    </div>

    <div style="margin-bottom: 1.5rem">
      <label>Commute Gap Minutes</label>
      <div class="hours-row" style="margin-top: 0.25rem">
        <input id="gap-slider" type="range" min="0" max="180" step="5"
          bind:value={commuteGapLocal} on:input={onGapSlider}
          style="flex:1"
        />
        <input id="gap-num" type="number" min="0" max="180" step="1"
          bind:value={commuteGapLocal} on:input={onGapNumber}
          style="width:80px"
        />
        <span class="hours-label">min</span>
      </div>
      <p class="info-text" style="margin-top: 0.5rem; font-size: 0.8rem">
        The required time gap between finishing at the office and starting at home. This gap is respected during rebalancing.
      </p>
    </div>

    <div>
      <label>Time Format</label>
      <div style="margin-top: 0.5rem; display: flex; gap: 1.5rem; align-items: center;">
        <label style="display: flex; gap: 0.35rem; font-weight: normal; cursor: pointer;">
          <input type="radio" bind:group={use24Local} value={true} />
          24-hour (14:30)
        </label>
        <label style="display: flex; gap: 0.35rem; font-weight: normal; cursor: pointer;">
          <input type="radio" bind:group={use24Local} value={false} />
          12-hour (2:30 PM)
        </label>
      </div>
    </div>

    <div style="margin-top: 1.5rem">
      <label>Work Off Days</label>
      <div style="margin-top: 0.5rem; display: flex; gap: 0.75rem 1.25rem; flex-wrap: wrap; align-items: center;">
        {#each DAY_OPTIONS as [name, idx]}
          <label style="display: flex; gap: 0.35rem; font-weight: normal; cursor: pointer; align-items: center;">
            <input
              type="checkbox"
              checked={offDaysLocal.includes(idx)}
              on:change={e => toggleOffDay(idx, e.target.checked)}
            />
            {name}
          </label>
        {/each}
      </div>
      <p class="info-text" style="margin-top: 0.5rem; font-size: 0.8rem">
        Hours logged on off days count as pure overtime (no required-hours deduction). Off days are shown with a muted background in the calendar and are excluded as recipients during rebalancing — their surplus hours can be redistributed to working days.
      </p>
    </div>

    <div style="margin-top: 1.5rem">
      <label>Rebalance History Limit</label>
      <div class="hours-row" style="margin-top: 0.25rem">
        <input type="number" min="0" max="100" step="1"
          bind:value={rebalHistoryCapLocal}
          on:input={e => rebalHistoryCapLocal = Math.max(0, parseInt(e.target.value) || 0)}
          style="width:80px"
        />
        <span class="hours-label">{rebalHistoryCapLocal === 0 ? 'unlimited' : 'entries / month'}</span>
      </div>
      <p class="info-text" style="margin-top: 0.5rem; font-size: 0.8rem">
        How many applied rebalances to remember per month. Set to 0 for unlimited. Older entries are pruned automatically when the limit is exceeded.
      </p>
    </div>

    <!-- Notifications -->
    <hr class="divider" />
    <p class="section-title">Notifications</p>
    {#if !window?.Capacitor?.isNativePlatform?.()}
      <p class="info-text" style="margin-bottom: 0.75rem; font-size: 0.78rem;">
        Notifications only fire on the Android app. Settings saved here sync via Supabase and take effect next time the app opens.
      </p>
    {/if}

      <!-- Morning check-in reminder -->
      <div class="notif-row">
        <div class="notif-info">
          <span class="notif-label">Morning check-in reminder</span>
          <span class="notif-desc">Reminds you to clock in on work days</span>
        </div>
        <label class="toggle">
          <input type="checkbox" checked={notifMorningEnabledLocal}
            on:change={e => toggleNotif(notifMorningEnabled, v => notifMorningEnabledLocal = v, e.target.checked)} />
          <span class="toggle-track"></span>
        </label>
      </div>
      {#if notifMorningEnabledLocal}
        <div class="notif-time-row">
          <label class="notif-time-label">Reminder time</label>
          <input type="time" bind:value={notifMorningTimeLocal} class="time-input" />
        </div>
      {/if}

      <hr class="divider" />

      <!-- Evening nudge -->
      <div class="notif-row">
        <div class="notif-info">
          <span class="notif-label">Evening nudge</span>
          <span class="notif-desc">Alerts if no work logged by end of day</span>
        </div>
        <label class="toggle">
          <input type="checkbox" checked={notifEveningEnabledLocal}
            on:change={e => toggleNotif(notifEveningEnabled, v => notifEveningEnabledLocal = v, e.target.checked)} />
          <span class="toggle-track"></span>
        </label>
      </div>
      {#if notifEveningEnabledLocal}
        <div class="notif-time-row">
          <label class="notif-time-label">Nudge time</label>
          <input type="time" bind:value={notifEveningTimeLocal} class="time-input" />
        </div>
      {/if}

      <hr class="divider" />

      <!-- Daily target reached -->
      <div class="notif-row">
        <div class="notif-info">
          <span class="notif-label">Daily target reached</span>
          <span class="notif-desc">Fires when you've worked your target hours</span>
        </div>
        <label class="toggle">
          <input type="checkbox" checked={notifTargetEnabledLocal}
            on:change={e => toggleNotif(notifTargetEnabled, v => notifTargetEnabledLocal = v, e.target.checked)} />
          <span class="toggle-track"></span>
        </label>
      </div>
      {#if notifTargetEnabledLocal}
        <div class="notif-time-row">
          <div>
            <span class="notif-time-label">Notify after</span>
            <span class="notif-desc" style="display:block; font-size:0.72rem; margin-top:2px">
              Default: {$requiredHours} h (required hours)
            </span>
          </div>
          <div style="display:flex; align-items:center; gap:0.4rem">
            <input type="number" min="1" max="14" step="0.5"
              value={notifTargetHoursLocal ?? ''}
              on:input={e => notifTargetHoursLocal = e.target.value ? parseFloat(e.target.value) : null}
              placeholder={String($requiredHours)}
              class="time-input" style="width:70px" />
            <span style="font-size:0.82rem; color:var(--color-text-muted)">h</span>
          </div>
        </div>
      {/if}

    <button class="btn btn-primary btn-full" style="margin-top:1.5rem" on:click={saveSettings}>
      💾 Save settings
    </button>

    <hr class="divider" />
    <p class="info-text">
      <strong>How overtime works:</strong> Daily OT = net worked − required hours. Cumulative monthly OT = sum of daily OTs for days with at least one log. Days with no logs (weekends, holidays) are not penalised.
    </p>
  </div>

  <!-- Export -->
  <div class="card">
    <p class="section-title">Export Logs by Month</p>
    <div class="export-row">
      <select bind:value={expYear} style="width:100px">
        {#each years as y}<option value={y}>{y}</option>{/each}
      </select>
      <select bind:value={expMonth}>
        {#each months as [v, label]}<option value={v}>{label}</option>{/each}
      </select>
    </div>
    <div style="margin-top: 0.6rem; display: flex; gap: 1.25rem; align-items: center; flex-wrap: wrap;">
      {#each [['all','All platforms'],['home','Home only'],['office','Office only']] as [val, lbl]}
        <label style="display: flex; gap: 0.35rem; font-weight: normal; cursor: pointer; font-size: 0.875rem;">
          <input type="radio" bind:group={expPlatform} value={val} />
          {lbl}
        </label>
      {/each}
      <label style="display: flex; gap: 0.35rem; font-weight: normal; cursor: pointer; font-size: 0.875rem; margin-left: auto;">
        <input type="checkbox" bind:checked={expCompact} />
        Compact (CSV only)
      </label>
      <label style="display: flex; gap: 0.35rem; font-weight: normal; cursor: pointer; font-size: 0.875rem;">
        <input type="checkbox" bind:checked={expHebrew} />
        עברית (CSV only)
      </label>
    </div>
    <div class="export-row">
      <button class="btn btn-primary" style="flex:1" on:click={doExport} disabled={expCount === 0}>
        ⬇ Export CSV
      </button>
      <button class="btn btn-secondary" style="flex:1" on:click={doExportJson} disabled={expCount === 0} title="Export as JSON — can be re-imported to restore this state">
        ⬇ Export JSON
      </button>
    </div>
    {#if expCount !== null}
      <p class="export-count">{expCount} record{expCount !== 1 ? 's' : ''} for this month</p>
    {/if}
  </div>

  <!-- Import -->
  <div class="card">
    <p class="section-title">Import Logs from JSON</p>
    <div class="import-modes">
      <div class="import-mode">
        <strong>Merge</strong>
        <span class="info-text">Upserts records by ID — existing logs not in the file are kept.</span>
      </div>
      <div class="import-mode">
        <strong>Replace</strong>
        <span class="info-text">Deletes all logs for the file's month(s) first, then inserts the imported records. True restore.</span>
      </div>
    </div>
    <input
      bind:this={importFileInput}
      type="file"
      accept=".json,application/json"
      on:change={e => importFile = e.target.files[0] ?? null}
      style="margin-top: 0.75rem; font-size: 0.875rem;"
    />
    <div class="export-row" style="margin-top: 0.75rem;">
      <button class="btn btn-secondary" style="flex:1" on:click={doImportMerge} disabled={!importFile || importing}>
        {importing ? '⏳…' : '⬆ Merge'}
      </button>
      <button class="btn btn-danger" style="flex:1" on:click={doImportReplace} disabled={!importFile || importing}>
        {importing ? '⏳…' : '⬆ Replace'}
      </button>
    </div>
  </div>

  <!-- Office Auto-Track -->
  <div class="card">
    <p class="section-title">Office Auto-Track (GPS)</p>
    <p class="info-text">
      Automatically resume/pause the <strong>Office</strong> timer when you arrive at or leave a saved location.
      {#if !window?.Capacitor?.isNativePlatform?.()}
        <br><em>On web this only works while the page is open. Install the Android app for true background tracking.</em>
      {/if}
    </p>

    {#each officeLocsLocal as loc (loc.id)}
      {@const isActive = loc.id === activeOfficeIdLocal}
      <div class="office-loc-card {isActive ? 'office-loc-active' : ''}">
        <div class="office-loc-header">
          <input class="loc-name-input" value={loc.name}
            on:blur={e => renameLocation(loc.id, e.target.value)}
            on:keydown={e => e.key === 'Enter' && e.target.blur()} />
          <span class="office-loc-coord">📍 {loc.lat.toFixed(5)}, {loc.lng.toFixed(5)}</span>
          <div class="office-loc-actions">
            {#if !isActive}
              <button class="btn btn-sm btn-secondary" on:click={() => setActive(loc.id)}>Make active</button>
            {:else}
              <span class="pill pill-primary">Active</span>
            {/if}
            <button class="btn btn-sm btn-danger" on:click={() => deleteLocation(loc.id)}>✕</button>
          </div>
        </div>

        {#if isActive}
          <div style="margin-top: 0.75rem;">
            <label style="font-size: 0.8rem;">Detection radius: <strong>{officeRadiusLocal}m</strong></label>
            <div class="hours-row" style="margin-top: 0.25rem;">
              <input type="range" min="50" max="2000" step="50"
                bind:value={officeRadiusLocal} on:change={updateActiveRadius} style="flex:1" />
              <input type="number" min="50" max="2000" step="50"
                bind:value={officeRadiusLocal} on:change={updateActiveRadius} style="width:80px" />
              <span class="hours-label">m</span>
            </div>
          </div>

          <div style="margin-top: 0.75rem;">
            <label style="font-size: 0.8rem;">Resume after being inside for: <strong>{resumeThresholdLocal}h</strong></label>
            <div class="hours-row" style="margin-top: 0.25rem;">
              <input type="range" min="0.25" max="8" step="0.25"
                bind:value={resumeThresholdLocal} on:change={updateThresholds} style="flex:1" />
              <input type="number" min="0.25" max="8" step="0.25"
                bind:value={resumeThresholdLocal} on:change={updateThresholds} style="width:80px" />
              <span class="hours-label">h</span>
            </div>
          </div>

          <div style="margin-top: 0.75rem;">
            <label style="font-size: 0.8rem;">Pause after being outside for: <strong>{pauseThresholdLocal}h</strong></label>
            <div class="hours-row" style="margin-top: 0.25rem;">
              <input type="range" min="0.25" max="8" step="0.25"
                bind:value={pauseThresholdLocal} on:change={updateThresholds} style="flex:1" />
              <input type="number" min="0.25" max="8" step="0.25"
                bind:value={pauseThresholdLocal} on:change={updateThresholds} style="width:80px" />
              <span class="hours-label">h</span>
            </div>
          </div>

          <div class="live-meter">
            {#if liveDistance !== null}
              {@const pct = Math.min(liveDistance / loc.radiusMeters * 100, 100)}
              <div class="live-meter-bar-track">
                <div class="live-meter-bar-fill {liveInside ? 'live-fill-in' : 'live-fill-out'}"
                  style="width: {pct}%"></div>
              </div>
              <div class="live-meter-label">
                <span>📡 {liveDistance.toLocaleString()} m from center</span>
                <span class="{liveInside ? 'live-text-in' : 'live-text-out'}">
                  {liveInside ? `✓ inside (${loc.radiusMeters} m radius)` : `✗ ${(liveDistance - loc.radiusMeters).toLocaleString()} m past edge`}
                </span>
              </div>
            {:else}
              <div class="live-meter-bar-track">
                <div class="live-meter-bar-fill live-fill-pending" style="width: 0%"></div>
              </div>
              <div class="live-meter-label">
                <span class="live-text-pending">📡 Waiting for GPS fix…</span>
              </div>
            {/if}
          </div>

          <div class="export-row" style="margin-top: 0.75rem;">
            <button class="btn btn-secondary" style="flex:1" on:click={updateActiveGPS} disabled={addingLocation}>
              {addingLocation ? '⏳…' : '📍 Update GPS'}
            </button>
            <button class="btn {autoTrackLocal ? 'btn-primary' : 'btn-secondary'}" style="flex:1" on:click={toggleAutoTrack}>
              {autoTrackLocal ? '✅ Auto-track ON' : '⏸ Auto-track OFF'}
            </button>
          </div>
        {/if}
      </div>
    {/each}

    <div class="office-add-row">
      <input type="text" placeholder="Name (e.g. Office, Branch…)" bind:value={newLocName}
        style="flex:1; min-width:120px" />
      <button class="btn btn-primary" on:click={captureAndAdd} disabled={addingLocation}
        style="white-space:nowrap">
        {addingLocation ? '⏳ Getting location…' : '📍 Add current location'}
      </button>
    </div>
    {#if officeLocsLocal.length === 0}
      <p class="info-text" style="margin-top: 0.5rem; font-size: 0.78rem;">
        Go to your office, enter a name (optional), then tap Add. Your GPS position will be saved.
      </p>
    {/if}
  </div>

  <!-- Account / Reconfigure -->
  <div class="card">
    <p class="section-title">Account &amp; Connection</p>
    <p class="info-text">Supabase project: <code>{maskedUrl}</code></p>
    <div class="account-actions">
      <button class="btn btn-secondary" style="flex:1" on:click={reconfigure}>🔧 Reconfigure</button>
      <button class="btn btn-danger" style="flex:1" on:click={signOut}>🚪 Sign out</button>
    </div>
  </div>
</div>

<style>
  .settings-screen { padding: 1.5rem; max-width: 620px; margin: 0 auto; }
  .page-title { font-size: 1.4rem; font-weight: 700; margin-bottom: 1.25rem; }
  .hours-row { display: flex; align-items: center; gap: 0.75rem; margin-top: 0.75rem; }
  .hours-label { font-size: 0.875rem; color: var(--color-text-muted); white-space: nowrap; }
  input[type="range"] { accent-color: var(--color-primary); }
  .export-row { display: flex; gap: 0.75rem; align-items: center; margin-top: 0.75rem; flex-wrap: wrap; }
  .import-modes { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-top: 0.5rem; }
  .import-mode { display: flex; flex-direction: column; gap: 0.2rem; padding: 0.5rem 0.75rem; border-radius: var(--radius-sm); background: var(--color-surface-2); border: 1px solid var(--color-border); font-size: 0.8rem; }
  .import-mode strong { font-size: 0.82rem; color: var(--color-text); }
  .export-count { font-size: 0.8rem; color: var(--color-text-muted); margin-top: 0.5rem; }
  .info-text { font-size: 0.875rem; color: var(--color-text-muted); line-height: 1.6; }
  .info-text code { font-size: 0.8rem; background: var(--color-surface-2); padding: 2px 6px; border-radius: 4px; }
  .account-actions { display: flex; gap: 0.75rem; margin-top: 1rem; flex-wrap: wrap; }
  .office-loc-card { margin-top: 0.75rem; padding: 0.75rem; background: var(--color-surface-2); border-radius: var(--radius-sm); border: 1.5px solid var(--color-border); }
  .office-loc-active { border-color: var(--color-primary); background: var(--color-primary-subtle); }
  .office-loc-header { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .loc-name-input { font-weight: 600; font-size: 0.9rem; border: none; border-bottom: 1px dashed var(--color-border); border-radius: 0; background: transparent; padding: 0 0 1px; width: auto; min-width: 60px; max-width: 160px; color: var(--color-text); }
  .loc-name-input:focus { outline: none; border-bottom-color: var(--color-primary); box-shadow: none; }
  .office-loc-coord { font-size: 0.75rem; font-family: monospace; color: var(--color-text-muted); }
  .office-loc-actions { display: flex; align-items: center; gap: 0.4rem; margin-left: auto; }
  .office-add-row { display: flex; gap: 0.75rem; margin-top: 1rem; flex-wrap: wrap; align-items: center; }
  .live-meter { margin-top: 0.75rem; }
  .live-meter-bar-track { height: 10px; background: var(--color-surface-2); border-radius: 999px; border: 1px solid var(--color-border); overflow: hidden; }
  .live-meter-bar-fill { height: 100%; border-radius: 999px; transition: width 0.6s ease, background 0.3s ease; }
  .live-fill-in  { background: var(--color-live); }
  .live-fill-out { background: var(--color-ot-neg); }
  .live-fill-pending { background: var(--color-border); }
  .live-meter-label { display: flex; justify-content: space-between; font-size: 0.78rem; color: var(--color-text-muted); margin-top: 0.35rem; flex-wrap: wrap; gap: 0.25rem; }
  .live-text-in  { color: var(--color-live); font-weight: 500; }
  .live-text-out { color: var(--color-ot-neg); font-weight: 500; }
  .live-text-pending { color: var(--color-text-muted); }

  /* ── Notifications ── */
  .notif-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-2) 0;
  }
  .notif-info { display: flex; flex-direction: column; gap: 2px; }
  .notif-label { font-size: 0.9rem; font-weight: 500; color: var(--color-text); }
  .notif-desc  { font-size: 0.78rem; color: var(--color-text-muted); }

  .notif-time-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-2) 0 var(--space-3);
  }
  .notif-time-label { font-size: 0.82rem; color: var(--color-text-muted); }
  .time-input { width: 120px; text-align: center; }

  /* iOS-style toggle */
  .toggle { position: relative; display: inline-block; width: 44px; height: 26px; flex-shrink: 0; cursor: pointer; }
  .toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
  .toggle-track {
    position: absolute; inset: 0;
    background: var(--color-border);
    border-radius: 13px;
    transition: background var(--transition);
  }
  .toggle-track::after {
    content: '';
    position: absolute;
    top: 3px; left: 3px;
    width: 20px; height: 20px;
    border-radius: 50%;
    background: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.25);
    transition: transform var(--transition);
  }
  .toggle input:checked + .toggle-track { background: var(--color-primary); }
  .toggle input:checked + .toggle-track::after { transform: translateX(18px); }
</style>
