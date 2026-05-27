<script>
  import { onMount, onDestroy } from 'svelte'
  import { requiredHours, minimumDailyHours, maximumDailyHours, commuteGapMinutes, use24HourFormat, offDays, dayOverrides, logs, screen, user, showToast, loading, officeLocation, autoTrackEnabled } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'
  import { exportCsv } from '../lib/exportUtils.js'
  import { monthBounds } from '../lib/timeUtils.js'

  let reqHoursLocal = 9
  requiredHours.subscribe(v => reqHoursLocal = v)

  let minHoursLocal = 5
  minimumDailyHours.subscribe(v => minHoursLocal = v)

  let maxHoursLocal = 12
  maximumDailyHours.subscribe(v => maxHoursLocal = v)

  let commuteGapLocal = 45
  commuteGapMinutes.subscribe(v => commuteGapLocal = v)

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
    const upsertRows = [
      { key: 'requiredDailyHours', value: String(reqHoursLocal) },
      { key: 'minimumDailyHours', value: String(minHoursLocal) },
      { key: 'maximumDailyHours', value: String(maxHoursLocal) },
      { key: 'commuteGapMinutes', value: String(commuteGapLocal) },
      { key: 'use24HourFormat', value: String(use24Local) },
      { key: 'offDays', value: JSON.stringify(offDaysLocal) },
    ]
    if (offDaysChanged) upsertRows.push({ key: 'dayOverrides', value: '{}' })
    const { error } = await sb.from('work_settings').upsert(upsertRows)
    if (error) showToast('Settings save failed: ' + error.message, 'error')
    else showToast('Settings saved ✓', 'success')
  }

  // ── Export ───────────────────────────────────────────────────
  const currentYear  = new Date().getFullYear()
  const currentMonth = new Date().getMonth() + 1
  let expYear  = currentYear
  let expMonth = currentMonth
  let expCount = null

  const years  = Array.from({ length: 5 }, (_, i) => currentYear - i)
  const months = [
    [1,'January'],[2,'February'],[3,'March'],[4,'April'],
    [5,'May'],[6,'June'],[7,'July'],[8,'August'],
    [9,'September'],[10,'October'],[11,'November'],[12,'December'],
  ]

  $: {
    const { start, end } = monthBounds(expYear, expMonth)
    expCount = $logs.filter(l => l.date_key >= start && l.date_key <= end).length
  }

  function doExport() {
    const { start, end } = monthBounds(expYear, expMonth)
    const subset = $logs.filter(l => l.date_key >= start && l.date_key <= end)
    if (!subset.length) { showToast('No logs for that month', 'info'); return }
    exportCsv(subset, `work-logs-${expYear}-${String(expMonth).padStart(2,'0')}.csv`, use24Local)
    showToast(`Exported ${subset.length} records`, 'success')
  }

  function doExportJson() {
    const { start, end } = monthBounds(expYear, expMonth)
    const subset = $logs.filter(l => l.date_key >= start && l.date_key <= end)
    if (!subset.length) { showToast('No logs for that month', 'info'); return }
    const monthDayOverrides = Object.fromEntries(
      Object.entries($dayOverrides).filter(([dk]) => dk >= start && dk <= end)
    )
    const fileName = `work-logs-${expYear}-${String(expMonth).padStart(2,'0')}.json`
    const payload = {
      exported_at: new Date().toISOString(),
      month: `${expYear}-${String(expMonth).padStart(2,'0')}`,
      day_schedule: monthDayOverrides,
      logs: subset,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = fileName; a.click()
    URL.revokeObjectURL(url)
    showToast(`Exported ${subset.length} records as JSON`, 'success')
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
  let officeLocLocal = null
  officeLocation.subscribe(v => officeLocLocal = v)

  let autoTrackLocal = false
  autoTrackEnabled.subscribe(v => autoTrackLocal = v)

  let officeRadiusLocal = 200  // metres
  $: if (officeLocLocal) officeRadiusLocal = officeLocLocal.radiusMeters

  let capturingLocation = false

  async function captureOfficeLocation() {
    if (!navigator?.geolocation) { showToast('Geolocation not available', 'error'); return }
    capturingLocation = true
    navigator.geolocation.getCurrentPosition(
      async pos => {
        capturingLocation = false
        const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude, radiusMeters: officeRadiusLocal }
        officeLocLocal = loc
        await saveOfficeLocation(loc)
      },
      err => {
        capturingLocation = false
        showToast('Could not get location: ' + err.message, 'error')
      },
      { enableHighAccuracy: true, timeout: 10_000 }
    )
  }

  async function saveOfficeLocation(loc) {
    officeLocation.set(loc)
    localStorage.setItem('whl_office_location', JSON.stringify(loc))
    const upsertRows = [{ key: 'officeLocation', value: JSON.stringify(loc) }]
    if (!autoTrackLocal) {
      autoTrackLocal = true
      autoTrackEnabled.set(true)
      localStorage.setItem('whl_auto_track', 'true')
      upsertRows.push({ key: 'autoTrackEnabled', value: 'true' })
    }
    const sb = getSupabase()
    const { error } = await sb.from('work_settings').upsert(upsertRows)
    if (error) showToast('Failed to save office location', 'error')
    else showToast('Office location saved ✓', 'success')
  }

  async function updateRadius() {
    if (!officeLocLocal) return
    const loc = { ...officeLocLocal, radiusMeters: officeRadiusLocal }
    await saveOfficeLocation(loc)
  }

  async function clearOfficeLocation() {
    officeLocLocal = null
    officeLocation.set(null)
    autoTrackLocal = false
    autoTrackEnabled.set(false)
    localStorage.removeItem('whl_office_location')
    localStorage.setItem('whl_auto_track', 'false')
    const sb = getSupabase()
    await sb.from('work_settings').upsert([
      { key: 'officeLocation', value: 'null' },
      { key: 'autoTrackEnabled', value: 'false' },
    ])
    showToast('Office location cleared', 'info')
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
        if (!officeLocLocal) { liveDistance = null; return }
        liveDistance = Math.round(_geodist(pos.coords.latitude, pos.coords.longitude, officeLocLocal.lat, officeLocLocal.lng))
      },
      () => {},
      { enableHighAccuracy: true, maximumAge: 5_000 }
    )
  })

  onDestroy(() => {
    if (liveWatchId !== null) navigator.geolocation.clearWatch(liveWatchId)
  })

  $: liveInside = liveDistance !== null && officeLocLocal ? liveDistance <= officeLocLocal.radiusMeters : null

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

    <button class="btn btn-primary" style="margin-top:1.5rem" on:click={saveSettings}>
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
      <button class="btn btn-primary" on:click={doExport} disabled={expCount === 0}>
        ⬇ Export CSV
      </button>
      <button class="btn btn-secondary" on:click={doExportJson} disabled={expCount === 0} title="Export as JSON — can be re-imported to restore this state">
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
    <div class="export-row" style="margin-top: 0.75rem;">
      <input
        bind:this={importFileInput}
        type="file"
        accept=".json,application/json"
        on:change={e => importFile = e.target.files[0] ?? null}
        style="flex: 1; font-size: 0.875rem;"
      />
      <button class="btn btn-secondary" on:click={doImportMerge} disabled={!importFile || importing}>
        {importing ? '⏳…' : '⬆ Merge'}
      </button>
      <button class="btn btn-primary" on:click={doImportReplace} disabled={!importFile || importing}>
        {importing ? '⏳…' : '⬆ Replace'}
      </button>
    </div>
  </div>

  <!-- Office Location / Auto-Track -->
  <div class="card">
    <p class="section-title">Office Auto-Track (GPS)</p>
    <p class="info-text">
      Automatically resume/pause the <strong>Office</strong> timer when you arrive at or leave your office.
      {#if !window?.Capacitor?.isNativePlatform?.()}
        <br><em>On web this only works while the page is open. Install the Android app for true background tracking.</em>
      {/if}
    </p>

    {#if officeLocLocal}
      <div class="office-loc-display">
        <span class="office-loc-coord">📍 {officeLocLocal.lat.toFixed(5)}, {officeLocLocal.lng.toFixed(5)}</span>
        <span class="office-loc-radius">Radius: {officeLocLocal.radiusMeters}m</span>
      </div>

      <div class="live-meter">
        {#if liveDistance !== null}
          {@const pct = Math.min(liveDistance / officeLocLocal.radiusMeters * 100, 100)}
          <div class="live-meter-bar-track">
            <div class="live-meter-bar-fill {liveInside ? 'live-fill-in' : 'live-fill-out'}"
              style="width: {pct}%"></div>
          </div>
          <div class="live-meter-label">
            <span>📡 {liveDistance.toLocaleString()} m from center</span>
            <span class="{liveInside ? 'live-text-in' : 'live-text-out'}">
              {liveInside ? `✓ inside (${officeLocLocal.radiusMeters} m radius)` : `✗ ${(liveDistance - officeLocLocal.radiusMeters).toLocaleString()} m past edge`}
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

      <div style="margin-top: 0.75rem;">
        <label for="radius-slider" style="font-size: 0.8rem;">Detection radius: <strong>{officeRadiusLocal}m</strong></label>
        <div class="hours-row" style="margin-top: 0.25rem;">
          <input id="radius-slider" type="range" min="50" max="1000" step="50"
            bind:value={officeRadiusLocal} on:change={updateRadius} style="flex:1" />
          <input type="number" min="50" max="1000" step="50"
            bind:value={officeRadiusLocal} on:change={updateRadius} style="width:80px" />
          <span class="hours-label">m</span>
        </div>
      </div>

      <div class="export-row" style="margin-top: 1rem;">
        <button class="btn btn-secondary" on:click={captureOfficeLocation} disabled={capturingLocation}>
          {capturingLocation ? '⏳ Getting location…' : '📍 Update location'}
        </button>
        <button class="btn {autoTrackLocal ? 'btn-primary' : 'btn-secondary'}" on:click={toggleAutoTrack}>
          {autoTrackLocal ? '✅ Auto-track ON' : '⏸ Auto-track OFF'}
        </button>
        <button class="btn btn-danger" on:click={clearOfficeLocation}>✕ Clear</button>
      </div>
    {:else}
      <div style="margin-top: 0.75rem;">
        <button class="btn btn-primary" on:click={captureOfficeLocation} disabled={capturingLocation}>
          {capturingLocation ? '⏳ Getting location…' : '📍 Set office location'}
        </button>
        <p class="info-text" style="margin-top: 0.5rem; font-size: 0.78rem;">
          Go to your office, then tap this button. Your current GPS position will be saved as the office location.
        </p>
      </div>
    {/if}
  </div>

  <!-- Account / Reconfigure -->
  <div class="card">
    <p class="section-title">Account &amp; Connection</p>
    <p class="info-text">Supabase project: <code>{maskedUrl}</code></p>
    <div class="account-actions">
      <button class="btn btn-secondary" on:click={reconfigure}>🔧 Reconfigure</button>
      <button class="btn btn-danger" on:click={signOut}>🚪 Sign out</button>
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
  .office-loc-display { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-top: 0.75rem; padding: 0.5rem 0.75rem; background: var(--color-surface-2); border-radius: var(--radius-sm); border: 1px solid var(--color-border); }
  .office-loc-coord { font-size: 0.85rem; font-family: monospace; color: var(--color-text); }
  .office-loc-radius { font-size: 0.8rem; color: var(--color-text-muted); }
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
</style>
