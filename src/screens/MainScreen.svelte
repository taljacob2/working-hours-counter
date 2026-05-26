<script>
  import { onDestroy } from 'svelte'
  import { logs, requiredHours, offDays, showToast } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'
  import { computeNetMs, computeTotalMs, fmtDuration, dateKey, byTs,
           loggedDaysInMonth, monthBounds, monthCumulativeOtMs, isOffDay } from '../lib/timeUtils.js'

  // ── Live clock ────────────────────────────────────────────────
  let now = new Date()
  const ticker = setInterval(() => now = new Date(), 1000)
  onDestroy(() => clearInterval(ticker))

  // ── Derived metrics ──────────────────────────────────────────
  $: todayKey = dateKey(now)
  $: todayLogs = $logs.filter(l => l.date_key === todayKey).sort(byTs)
  $: todayNetMs = computeNetMs(todayLogs, now)
  $: todayTotalMs = computeTotalMs(todayLogs)
  $: reqMs = $requiredHours * 3_600_000
  $: todayIsOffDay = isOffDay(todayKey, $offDays)
  $: todayOtMs = todayIsOffDay ? todayNetMs : todayNetMs - reqMs

  $: thisYear  = now.getFullYear()
  $: thisMonth = now.getMonth() + 1
  $: monthLogs = $logs.filter(l => {
    const { start, end } = monthBounds(thisYear, thisMonth)
    return l.date_key >= start && l.date_key <= end
  })
  $: monthNetMs   = (() => {
    const days = loggedDaysInMonth($logs, thisYear, thisMonth)
    return days.reduce((acc, dk) => {
      const dl = $logs.filter(l => l.date_key === dk).sort(byTs)
      return acc + computeNetMs(dl, dk === todayKey ? now : null)
    }, 0)
  })()
  $: monthTotalMs = (() => {
    const days = loggedDaysInMonth($logs, thisYear, thisMonth)
    return days.reduce((acc, dk) => {
      const dl = $logs.filter(l => l.date_key === dk).sort(byTs)
      return acc + computeTotalMs(dl)
    }, 0)
  })()
  $: cumOtMs = monthCumulativeOtMs($logs, thisYear, thisMonth, $requiredHours, $offDays)

  // ── Platform state ───────────────────────────────────────────
  function platformState(platform, todayLogsArray) {
    const pl = todayLogsArray.filter(l => l.platform === platform)
    if (!pl.length) return 'idle'
    return pl[pl.length - 1].action === 'resume' ? 'live' : 'paused'
  }
  function platformNetMs(platform, todayLogsArray, currentTime) {
    const pl = todayLogsArray.filter(l => l.platform === platform).sort(byTs)
    return computeNetMs(pl, platformState(platform, todayLogsArray) === 'live' ? currentTime : null)
  }

  // ── Button press handler ─────────────────────────────────────
  async function press(platform, action) {
    // Idempotency check
    const last = todayLogs.filter(l => l.platform === platform).at(-1)
    if (last && last.action === action) {
      showToast(`${platform} already ${action}d — duplicate ignored`, 'info')
      return
    }
    const entry = {
      id: crypto.randomUUID(),
      platform,
      action,
      timestamp: new Date().toISOString(),
      date_key: todayKey,
      created_at: new Date().toISOString(),
      note: '',
    }
    const sb = getSupabase()
    const { error } = await sb.from('work_logs').insert(entry)
    if (error) { showToast('Save failed: ' + error.message, 'error'); return }
    logs.update(l => [...l, entry])
    showToast(`${platform === 'office' ? '🏢' : '🏠'} ${platform} ${action}d`, 'success')
  }
</script>

<div class="main-screen">
  <!-- ── Today metrics ── -->
  <section class="section">
    <p class="section-title">Today — {todayKey}</p>
    <div class="metrics-row">
      <div class="metric-card">
        <span class="metric-label">Net worked</span>
        <span class="metric-value tabnum">{fmtDuration(todayNetMs)}</span>
      </div>
      <div class="metric-card ot-card" class:ot-pos={todayOtMs >= 0} class:ot-neg={todayOtMs < 0}>
        <span class="metric-label">Today OT</span>
        <span class="metric-value tabnum">{fmtDuration(todayOtMs, true)}</span>
        <span class="ot-hint">
          {#if todayOtMs >= 0}🚀 Ahead by {fmtDuration(todayOtMs)}{:else}⏰ Need {fmtDuration(-todayOtMs)} more{/if}
        </span>
      </div>
      <div class="metric-card">
        <span class="metric-label">Gross total</span>
        <span class="metric-value tabnum">{fmtDuration(todayTotalMs)}</span>
      </div>
    </div>
  </section>

  <!-- ── Month metrics ── -->
  <section class="section">
    <p class="section-title">This Month</p>
    <div class="metrics-row">
      <div class="metric-card">
        <span class="metric-label">Month net</span>
        <span class="metric-value tabnum">{fmtDuration(monthNetMs)}</span>
      </div>
      <div class="metric-card ot-card" class:ot-pos={cumOtMs >= 0} class:ot-neg={cumOtMs < 0}>
        <span class="metric-label">Cumulative OT</span>
        <span class="metric-value tabnum">{fmtDuration(cumOtMs, true)}</span>
      </div>
      <div class="metric-card">
        <span class="metric-label">Month gross</span>
        <span class="metric-value tabnum">{fmtDuration(monthTotalMs)}</span>
      </div>
    </div>
    <!-- OT Banner -->
    <div class="ot-banner" class:ot-pos={cumOtMs >= 0} class:ot-neg={cumOtMs < 0}>
      {#if cumOtMs >= 0}
        🚀 You're <strong>{fmtDuration(cumOtMs)}</strong> ahead this month — you can leave early!
      {:else}
        ⏰ You need <strong>{fmtDuration(-cumOtMs)}</strong> more to catch up this month.
      {/if}
    </div>
  </section>

  <!-- ── Platform buttons ── -->
  <section class="section">
    <div class="platforms">
      {#each ['office', 'home'] as platform}
        {@const state = platformState(platform, todayLogs)}
        {@const netMs = platformNetMs(platform, todayLogs, now)}
        <div class="platform-card platform--{platform}">
          <div class="platform-header">
            <span class="platform-icon">{platform === 'office' ? '🏢' : '🏠'}</span>
            <span class="platform-name">{platform === 'office' ? 'Office' : 'Home'}</span>
            <span class="pill {state === 'live' ? 'pill-live' : state === 'paused' ? 'pill-muted' : 'pill-muted'}">
              {state === 'live' ? '● Live' : state === 'paused' ? '⏸ Paused' : '○ Idle'}
            </span>
          </div>
          <div class="platform-net tabnum">{fmtDuration(netMs)}</div>
          <div class="platform-btns">
            <button
              class="action-btn resume-btn"
              class:active={state === 'live'}
              on:click={() => press(platform, 'resume')}
              disabled={state === 'live'}
            >
              ▶ Resume / Enter
            </button>
            <button
              class="action-btn pause-btn"
              class:active={state === 'paused'}
              on:click={() => press(platform, 'pause')}
              disabled={state !== 'live'}
            >
              ⏸ Pause / Exit
            </button>
          </div>
        </div>
      {/each}
    </div>
  </section>
</div>

<style>
  .main-screen { padding: 1.5rem; max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: 1.5rem; }
  .section { display: flex; flex-direction: column; gap: 0.75rem; }

  /* Metric cards */
  .metrics-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }
  @media (max-width: 540px) { .metrics-row { grid-template-columns: 1fr; } }
  .metric-card {
    background: var(--color-surface); border: 1px solid var(--color-border);
    border-radius: var(--radius-md); padding: 1rem 1.25rem;
    display: flex; flex-direction: column; gap: 0.25rem;
    box-shadow: var(--shadow-sm);
  }
  .metric-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted); }
  .metric-value { font-size: 1.75rem; font-weight: 700; line-height: 1.1; }
  .ot-hint { font-size: 0.75rem; color: inherit; margin-top: 2px; }
  .ot-card.ot-pos { border-color: var(--color-ot-pos); background: var(--color-ot-pos-subtle); color: var(--color-ot-pos); }
  .ot-card.ot-neg { border-color: var(--color-ot-neg); background: var(--color-ot-neg-subtle); color: var(--color-ot-neg); }
  .ot-card .metric-label { color: inherit; opacity: 0.75; }

  /* OT Banner */
  .ot-banner {
    padding: 0.75rem 1.25rem; border-radius: var(--radius-sm);
    font-size: 0.9rem;
  }
  .ot-banner.ot-pos { background: var(--color-ot-pos-subtle); color: var(--color-ot-pos); border: 1px solid var(--color-ot-pos); }
  .ot-banner.ot-neg { background: var(--color-ot-neg-subtle); color: var(--color-ot-neg); border: 1px solid var(--color-ot-neg); }

  /* Platform cards */
  .platforms { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  @media (max-width: 540px) { .platforms { grid-template-columns: 1fr; } }
  .platform-card {
    background: var(--color-surface); border: 1.5px solid var(--color-border);
    border-radius: var(--radius-md); padding: 1.25rem;
    display: flex; flex-direction: column; gap: 0.75rem;
    box-shadow: var(--shadow-sm);
    transition: border-color var(--transition);
  }
  .platform--office { border-top: 4px solid var(--color-office); }
  .platform--home   { border-top: 4px solid var(--color-home); }
  .platform-header { display: flex; align-items: center; gap: 0.5rem; }
  .platform-icon { font-size: 1.25rem; }
  .platform-name { font-weight: 700; font-size: 1rem; flex: 1; text-transform: capitalize; }
  .platform-net { font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; }
  .platform-btns { display: flex; flex-direction: column; gap: 0.5rem; }
  .action-btn {
    padding: 0.625rem 1rem; border-radius: var(--radius-sm);
    font-size: 0.9375rem; font-weight: 600; min-height: 48px;
    border: 2px solid transparent; transition: all var(--transition);
  }
  .resume-btn {
    background: var(--color-ot-pos-subtle); color: var(--color-ot-pos);
    border-color: var(--color-ot-pos);
  }
  .resume-btn:hover:not(:disabled) { background: var(--color-ot-pos); color: #fff; }
  .resume-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .pause-btn {
    background: var(--color-surface-2); color: var(--color-text-muted);
    border-color: var(--color-border);
  }
  .pause-btn:hover:not(:disabled) { background: var(--color-ot-neg-subtle); color: var(--color-ot-neg); border-color: var(--color-ot-neg); }
  .pause-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .action-btn.active { box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 25%, transparent); }
</style>
