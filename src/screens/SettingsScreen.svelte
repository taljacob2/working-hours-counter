<script>
  import { requiredHours, logs, screen, user, showToast, loading } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'
  import { exportCsv } from '../lib/exportUtils.js'
  import { monthBounds } from '../lib/timeUtils.js'

  let reqHoursLocal = 9
  requiredHours.subscribe(v => reqHoursLocal = v)

  // Sync slider ↔ number input
  function onSlider(e)  { reqHoursLocal = parseFloat(e.target.value) }
  function onNumber(e)  { reqHoursLocal = Math.min(14, Math.max(4, parseFloat(e.target.value) || 9)) }

  async function saveSettings() {
    requiredHours.set(reqHoursLocal)
    localStorage.setItem('whl_req_hours', String(reqHoursLocal))
    const sb = getSupabase()
    const { error } = await sb.from('work_settings')
      .upsert({ key: 'requiredDailyHours', value: String(reqHoursLocal) })
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
    exportCsv(subset, `work-logs-${expYear}-${String(expMonth).padStart(2,'0')}.csv`)
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

  <!-- Required Hours -->
  <div class="card">
    <p class="section-title">Required Daily Hours</p>
    <div class="hours-row">
      <input id="req-slider" type="range" min="4" max="14" step="0.5"
        bind:value={reqHoursLocal} on:input={onSlider}
        style="flex:1"
      />
      <input id="req-num" type="number" min="4" max="14" step="0.5"
        bind:value={reqHoursLocal} on:input={onNumber}
        style="width:80px"
      />
      <span class="hours-label">h / day</span>
    </div>
    <button class="btn btn-primary" style="margin-top:1rem" on:click={saveSettings}>
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
