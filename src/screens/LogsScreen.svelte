<script>
  import { onDestroy } from 'svelte'
  import { logs, selectedDate, calCursor, logResolution, editingLogId, selectedDayLogs, showToast } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'
  import { fmtDuration, dateKey, computeNetMs, computeTotalMs, byTs,
           loggedDaysInMonth, monthBounds, monthCumulativeOtMs } from '../lib/timeUtils.js'
  import { requiredHours, minimumDailyHours, use24HourFormat } from '../stores/appStore.js'

  // Live clock for open-ended spans
  let now = new Date()
  const ticker = setInterval(() => now = new Date(), 1000)
  onDestroy(() => clearInterval(ticker))

  const todayKey = dateKey()
  let filterUnderMin = false

  // ── Calendar helpers ─────────────────────────────────────────
  const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

  $: calYear  = $calCursor.getFullYear()
  $: calMonth = $calCursor.getMonth() + 1

  $: calDays = buildCalendar(calYear, calMonth)
  $: cumOt   = monthCumulativeOtMs($logs, calYear, calMonth, $requiredHours)
  $: daysLogged = loggedDaysInMonth($logs, calYear, calMonth).length

  function buildCalendar(year, month) {
    const first = new Date(year, month - 1, 1)
    const last  = new Date(year, month, 0)
    const cells = []
    // Leading empties
    for (let i = 0; i < first.getDay(); i++) cells.push(null)
    for (let d = 1; d <= last.getDate(); d++) {
      const key = `${year}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`
      const dl  = $logs.filter(l => l.date_key === key).sort(byTs)
      const isOpen = dl.length > 0 && dl.at(-1).action === 'resume'
      const netMs  = computeNetMs(dl, (isOpen && key === todayKey) ? now : (isOpen ? null : null))
      const reqMs  = $requiredHours * 3_600_000
      const minMs  = $minimumDailyHours * 3_600_000
      const otMs   = dl.length > 0 ? netMs - reqMs : null
      const offMs  = computeNetMs(dl.filter(l => l.platform === 'office'), (isOpen && key === todayKey) ? now : null)
      const homeMs = computeNetMs(dl.filter(l => l.platform === 'home'),   (isOpen && key === todayKey) ? now : null)
      const underMin = netMs > 0 && netMs < minMs
      cells.push({ d, key, count: dl.length, netMs, otMs, offMs, homeMs, underMin })
    }
    return cells
  }

  function prevMonth() { calCursor.update(c => new Date(c.getFullYear(), c.getMonth() - 1, 1)) }
  function nextMonth() { calCursor.update(c => new Date(c.getFullYear(), c.getMonth() + 1, 1)) }
  function goToday()   { calCursor.set(new Date(new Date().getFullYear(), new Date().getMonth(), 1)); selectedDate.set(todayKey) }

  // ── Edit state ───────────────────────────────────────────────
  let editForm = null

  function startEdit(log) {
    editingLogId.set(log.id)
    editForm = {
      id:         log.id,
      timestamp:  log.timestamp.slice(0,16), // datetime-local format
      platform:   log.platform,
      action:     log.action,
      note:       log.note || '',
      created_at: log.created_at,
      isNew:      false
    }
  }

  function startNewLog() {
    editingLogId.set('new')
    const selDate = new Date($selectedDate + 'T09:00:00')
    // If it's today, maybe use current time?
    const d = $selectedDate === todayKey ? new Date() : selDate
    
    editForm = {
      id:         null,
      timestamp:  new Date(d.getTime() - d.getTimezoneOffset()*60000).toISOString().slice(0,16),
      platform:   'office',
      action:     'resume',
      note:       '',
      created_at: '(will be set on save)',
      isNew:      true
    }
  }
  function cancelEdit() { editingLogId.set(null); editForm = null }

  let isSaving = false

  async function saveEdit() {
    isSaving = true
    const sb = getSupabase()
    const payload = {
      timestamp:  new Date(editForm.timestamp).toISOString(),
      platform:   editForm.platform,
      action:     editForm.action,
      note:       editForm.note,
      date_key:   editForm.timestamp.slice(0,10),
    }

    if (editForm.isNew) {
      const payloadWithId = { ...payload, id: crypto.randomUUID() }
      const { data, error } = await sb.from('work_logs').insert([payloadWithId]).select()
      isSaving = false
      if (error) { showToast('Save failed: ' + error.message, 'error'); return }
      logs.update(ls => [...ls, data[0]])
      showToast('Log added', 'success')
    } else {
      const { error } = await sb.from('work_logs').update(payload).eq('id', editForm.id)
      isSaving = false
      if (error) { showToast('Update failed: ' + error.message, 'error'); return }
      logs.update(ls => ls.map(l => l.id === editForm.id ? { ...l, ...payload } : l))
      showToast('Log updated', 'success')
    }
    cancelEdit()
  }

  async function deleteLog() {
    if (!window.confirm('Delete this log entry?')) return
    isSaving = true
    const sb = getSupabase()
    const { error } = await sb.from('work_logs').delete().eq('id', editForm.id)
    isSaving = false
    if (error) { showToast('Delete failed: ' + error.message, 'error'); return }
    logs.update(ls => ls.filter(l => l.id !== editForm.id))
    showToast('Log deleted', 'info')
    cancelEdit()
  }

  // ── Selected day metrics ─────────────────────────────────────
  $: selNetMs  = computeNetMs($selectedDayLogs, $selectedDate === todayKey ? now : null)
  $: selOtMs   = $selectedDayLogs.length > 0 ? selNetMs - $requiredHours * 3_600_000 : null

  // ── Format helpers ───────────────────────────────────────────
  function fmtTs(ts) {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: !$use24HourFormat })
  }
  function fmtDate(ts) {
    return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
  }

  const MONTH_NAMES = ['January','February','March','April','May','June',
    'July','August','September','October','November','December']
</script>

<div class="logs-screen">
  <!-- LEFT: Calendar -->
  <aside class="cal-panel">
    <div class="cal-nav">
      <button class="btn btn-secondary btn-sm" on:click={prevMonth}>‹</button>
      <div class="cal-title">
        <strong>{MONTH_NAMES[calMonth-1]} {calYear}</strong>
        <div class="cal-month-pills">
          <span class="pill pill-muted">{daysLogged}d logged</span>
          <span class="pill {cumOt >= 0 ? 'pill-ot-pos' : 'pill-ot-neg'}">{fmtDuration(cumOt, true)} OT</span>
          <button 
            class="pill {filterUnderMin ? 'pill-ot-neg' : 'pill-muted'}" 
            style="cursor: pointer; border: 1.5px solid transparent;" 
            class:active-filter={filterUnderMin}
            on:click={() => filterUnderMin = !filterUnderMin}
            title="Filter by under minimum"
          >
            ⚠ Filter Under Min
          </button>
        </div>
      </div>
      <div class="cal-nav-right">
        <button class="btn btn-secondary btn-sm" on:click={goToday}>Today</button>
        <button class="btn btn-secondary btn-sm" on:click={nextMonth}>›</button>
      </div>
    </div>

    <div class="cal-grid">
      {#each DAY_NAMES as dn}
        <div class="cal-day-name">{dn}</div>
      {/each}
      {#each calDays as cell}
        {#if cell === null}
          <div class="cal-cell cal-cell--empty"></div>
        {:else}
          <button
            class="cal-cell"
            class:cal-cell--today={cell.key === todayKey}
            class:cal-cell--selected={cell.key === $selectedDate}
            class:cal-cell--ot-pos={cell.otMs !== null && cell.otMs >= 0}
            class:cal-cell--ot-neg={cell.otMs !== null && cell.otMs < 0}
            class:cal-cell--under-min={cell.underMin}
            class:cal-cell--filtered-out={filterUnderMin && !cell.underMin}
            on:click={() => selectedDate.set(cell.key)}
          >
            <span class="cal-day-num">{cell.d}</span>
            {#if cell.count > 0}
              <span class="cal-net tabnum">{fmtDuration(cell.netMs)}</span>
              {#if cell.otMs !== null}
                <span class="cal-ot tabnum {cell.otMs >= 0 ? 'pos' : 'neg'}">{fmtDuration(cell.otMs, true)}</span>
              {/if}
            {/if}
          </button>
        {/if}
      {/each}
    </div>
  </aside>

  <!-- RIGHT: Day logs -->
  <main class="day-panel">
    <div class="day-header">
      <h2>{new Date($selectedDate + 'T12:00:00').toLocaleDateString([], { weekday:'long', month:'long', day:'numeric', year:'numeric' })}</h2>
      <div class="day-pills">
        <span class="pill pill-primary tabnum">Net {fmtDuration(selNetMs)}</span>
        {#if selOtMs !== null}
          <span class="pill {selOtMs >= 0 ? 'pill-ot-pos' : 'pill-ot-neg'} tabnum">{fmtDuration(selOtMs, true)} OT</span>
        {/if}
        <span class="pill pill-muted">{$selectedDayLogs.length} logs</span>
        <select bind:value={$logResolution} class="res-select">
          <option value="compact">Compact</option>
          <option value="full">Full</option>
        </select>
        <button class="btn btn-sm btn-primary" on:click={startNewLog}>+ Add Log</button>
      </div>
    </div>

    {#if selNetMs > 0 && selNetMs < $minimumDailyHours * 3_600_000}
      <div class="min-hours-warning">
        ⚠️ You logged <strong>{fmtDuration(selNetMs)}</strong>, which is below your minimum daily target of <strong>{$minimumDailyHours}h</strong>.
      </div>
    {/if}

    {#if $selectedDayLogs.length === 0}
      <div class="empty-state">
        <p>No logs for this day.</p>
        <button class="btn btn-primary" on:click={startNewLog}>Add your first log</button>
      </div>
    {:else}
      <div class="log-table-wrap">
        <table class="log-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Platform</th>
              <th>Action</th>
              {#if $logResolution === 'full'}<th>Date</th>{/if}
              <th>Note</th>
              {#if $logResolution === 'full'}<th>Created</th>{/if}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each $selectedDayLogs as log (log.id)}
              <tr class:editing={$editingLogId === log.id}>
                <td class="tabnum">{fmtTs(log.timestamp)}</td>
                <td>
                  <span class="pill pill-{log.platform === 'office' ? 'office' : 'home'}">{log.platform}</span>
                </td>
                <td>
                  <span class="pill {log.action === 'resume' ? 'pill-live' : 'pill-muted'}">{log.action}</span>
                </td>
                {#if $logResolution === 'full'}<td class="tabnum muted">{fmtDate(log.timestamp)}</td>{/if}
                <td class="note-cell">{log.note || '—'}</td>
                {#if $logResolution === 'full'}<td class="muted tabnum">{fmtTs(log.created_at)}</td>{/if}
                <td>
                  <button class="btn btn-sm btn-secondary" on:click={() => startEdit(log)}>✏️ Edit</button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    <!-- Edit panel -->
    {#if editForm}
      <div class="edit-panel card">
        <h3>{editForm.isNew ? 'Add New Log' : 'Edit Log'}</h3>
        <div class="edit-grid">
          <div class="field">
            <label for="edit-ts">Timestamp</label>
            <input id="edit-ts" type="datetime-local" bind:value={editForm.timestamp} />
          </div>
          <div class="field">
            <label for="edit-platform">Platform</label>
            <select id="edit-platform" bind:value={editForm.platform}>
              <option value="office">Office</option>
              <option value="home">Home</option>
            </select>
          </div>
          <div class="field">
            <label for="edit-action">Action</label>
            <select id="edit-action" bind:value={editForm.action}>
              <option value="resume">Resume</option>
              <option value="pause">Pause</option>
            </select>
          </div>
          <div class="field">
            <label for="edit-created">Created at (read-only)</label>
            <input id="edit-created" type="text" value={editForm.created_at} disabled />
          </div>
        </div>
        <div class="field" style="margin-top:0.75rem">
          <label for="edit-note">Note</label>
          <textarea id="edit-note" rows="2" bind:value={editForm.note} placeholder="Optional note…"></textarea>
        </div>
        <div class="edit-actions">
          <button class="btn btn-primary" on:click={saveEdit} disabled={isSaving}>
            {editForm.isNew ? '➕ Create Log' : '💾 Save'}
          </button>
          <button class="btn btn-secondary" on:click={cancelEdit} disabled={isSaving}>Cancel</button>
          {#if !editForm.isNew}
            <button class="btn btn-danger" on:click={deleteLog} disabled={isSaving}>🗑 Delete</button>
          {/if}
        </div>
      </div>
    {/if}
  </main>
</div>

<style>
  .logs-screen {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 1.5rem;
    padding: 1.5rem;
    max-width: 1200px;
    margin: 0 auto;
    min-height: calc(100dvh - 56px);
    align-items: start;
  }
  @media (max-width: 780px) {
    .logs-screen { 
      grid-template-columns: minmax(0, 1fr); 
      padding: 0.25rem;
      gap: 0.5rem;
      overflow-x: hidden;
    }
    .cal-panel {
      position: relative !important;
      top: auto !important;
      padding: 0.25rem;
    }
    .cal-nav { gap: 0.25rem; }
    .cal-nav .btn { padding: 0.25rem 0.5rem; }
    .cal-grid { gap: 1px; }
    .cal-cell { padding: 2px 0; min-height: 44px; min-width: 0; overflow: hidden; }
    .cal-net, .cal-ot { font-size: 0.55rem; letter-spacing: -0.5px; white-space: nowrap; text-overflow: clip; max-width: 100%; text-align: center; }
    .cal-day-num { font-size: 0.7rem; }
    .cal-month-pills { gap: 0.125rem; }
  }

  /* Calendar */
  .cal-panel { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 1rem; box-shadow: var(--shadow-sm); position: sticky; top: 72px; }
  .cal-nav { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
  .cal-title { flex: 1; text-align: center; font-size: 0.95rem; }
  .cal-month-pills { display: flex; gap: 0.375rem; justify-content: center; margin-top: 0.25rem; flex-wrap: wrap; }
  .cal-nav-right { display: flex; gap: 0.25rem; }
  .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
  .cal-day-name { text-align: center; font-size: 0.7rem; font-weight: 700; color: var(--color-text-muted); padding: 4px 0; text-transform: uppercase; }
  .cal-cell--empty { background: transparent; }
  .cal-cell {
    background: var(--color-surface-2); border: 1.5px solid transparent;
    border-radius: var(--radius-sm); padding: 4px 3px;
    display: flex; flex-direction: column; align-items: center; gap: 1px;
    cursor: pointer; min-height: 56px; transition: border-color var(--transition), background var(--transition);
  }
  .cal-cell:hover { border-color: var(--color-primary); background: var(--color-primary-subtle); }
  .cal-cell--today .cal-day-num { background: var(--color-primary); color: #fff; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; }
  .cal-cell--selected { border-color: var(--color-primary) !important; box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 30%, transparent); }
  .cal-cell--ot-pos { border-left: 3px solid var(--color-ot-pos); }
  .cal-cell--ot-neg { border-left: 3px solid var(--color-ot-neg); }
  .cal-cell--under-min { box-shadow: inset 0 0 0 1.5px var(--color-ot-neg); }
  .cal-cell--filtered-out { opacity: 0.15; pointer-events: none; }
  .active-filter { border-color: color-mix(in srgb, var(--color-ot-neg) 30%, transparent) !important; }
  .cal-day-num { font-size: 0.8rem; font-weight: 600; }
  .cal-net { font-size: 0.65rem; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
  .cal-ot { font-size: 0.65rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .cal-ot.pos { color: var(--color-ot-pos); }
  .cal-ot.neg { color: var(--color-ot-neg); }

  /* Day panel */
  .day-panel { display: flex; flex-direction: column; gap: 1rem; }
  .day-header { display: flex; flex-direction: column; gap: 0.5rem; }
  h2 { font-size: 1.1rem; font-weight: 700; }
  .day-pills { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .res-select { width: auto; padding: 2px 8px; font-size: 0.8rem; min-height: 28px; }
  .min-hours-warning {
    padding: 0.75rem 1rem; border-radius: var(--radius-sm);
    background: var(--color-ot-neg-subtle); color: var(--color-ot-neg);
    font-size: 0.85rem; border: 1px solid color-mix(in srgb, var(--color-ot-neg) 30%, transparent);
  }
  .empty-state { text-align: center; color: var(--color-text-muted); padding: 3rem 0; font-size: 0.9rem; }

  /* Log table */
  .log-table-wrap { overflow-x: auto; border-radius: var(--radius-md); border: 1px solid var(--color-border); }
  .log-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  .log-table thead { background: var(--color-surface-2); }
  .log-table th { padding: 0.5rem 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 700; color: var(--color-text-muted); white-space: nowrap; }
  .log-table td { padding: 0.5rem 0.75rem; border-top: 1px solid var(--color-border); }
  .log-table tr:hover td { background: var(--color-surface-2); }
  .log-table tr.editing td { background: var(--color-primary-subtle); }
  .note-cell { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text-muted); }
  .muted { color: var(--color-text-muted); }

  /* Edit panel */
  .edit-panel { margin-top: 0.5rem; }
  h3 { font-size: 1rem; font-weight: 700; margin-bottom: 1rem; }
  .edit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  @media (max-width: 540px) { .edit-grid { grid-template-columns: 1fr; } }
  .edit-actions { display: flex; gap: 0.5rem; margin-top: 1rem; flex-wrap: wrap; }
</style>
