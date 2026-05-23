<script>
  import { requiredHours, minimumDailyHours, maximumDailyHours, commuteGapMinutes, use24HourFormat, logs, screen, user, showToast, loading } from '../stores/appStore.js'
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

    const sb = getSupabase()
    const { error } = await sb.from('work_settings').upsert([
      { key: 'requiredDailyHours', value: String(reqHoursLocal) },
      { key: 'minimumDailyHours', value: String(minHoursLocal) },
      { key: 'maximumDailyHours', value: String(maxHoursLocal) },
      { key: 'commuteGapMinutes', value: String(commuteGapLocal) },
      { key: 'use24HourFormat', value: String(use24Local) }
    ])
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
    </div>
    {#if expCount !== null}
      <p class="export-count">{expCount} record{expCount !== 1 ? 's' : ''} for this month</p>
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
  .export-count { font-size: 0.8rem; color: var(--color-text-muted); margin-top: 0.5rem; }
  .info-text { font-size: 0.875rem; color: var(--color-text-muted); line-height: 1.6; }
  .info-text code { font-size: 0.8rem; background: var(--color-surface-2); padding: 2px 6px; border-radius: 4px; }
  .account-actions { display: flex; gap: 0.75rem; margin-top: 1rem; flex-wrap: wrap; }
</style>
