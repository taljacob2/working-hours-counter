<script>
  import { onDestroy } from 'svelte'
  import { logs, requiredHours, minimumDailyHours, offDays, dayOverrides } from '../stores/appStore.js'
  import { computeNetMs, byTs, isOffDay, dateKey, fmtDuration, monthCumulativeOtMs } from '../lib/timeUtils.js'

  let now = new Date()
  const ticker = setInterval(() => { now = new Date() }, 60_000)
  onDestroy(() => clearInterval(ticker))

  let period = 'week'

  const _today = new Date()
  const currentYear  = _today.getFullYear()
  const currentMonth = _today.getMonth() + 1

  // ── Date helpers ─────────────────────────────────────────────

  function getLastNDays(n) {
    const days = []
    for (let i = n - 1; i >= 0; i--) {
      const d = new Date(now)
      d.setDate(now.getDate() - i)
      days.push(dateKey(d))
    }
    return days
  }

  function getCurrentMonthDays() {
    const daysInMonth = new Date(currentYear, currentMonth, 0).getDate()
    const days = []
    for (let d = 1; d <= daysInMonth; d++) {
      days.push(`${currentYear}-${String(currentMonth).padStart(2,'0')}-${String(d).padStart(2,'0')}`)
    }
    return days
  }

  function dayNetMs(dk, logsArr, currentTime) {
    const dayLogs = logsArr.filter(l => l.date_key === dk).sort(byTs)
    const isOpen  = dayLogs.length > 0 && dayLogs.at(-1).action === 'resume'
    return computeNetMs(dayLogs, isOpen && dk === dateKey(currentTime) ? currentTime : null)
  }

  function monthName() {
    return new Date(currentYear, currentMonth - 1, 1)
      .toLocaleString('default', { month: 'long' })
  }

  // ── Reactive chart data ──────────────────────────────────────

  $: todayDk = dateKey(now)

  $: chartDays = period === 'week' ? getLastNDays(7) : getCurrentMonthDays()

  $: dayData = chartDays.map(dk => {
    const netMs   = dayNetMs(dk, $logs, now)
    const isOff   = isOffDay(dk, $offDays, $dayOverrides)
    const isFuture = dk > todayDk
    const hasLogs  = $logs.some(l => l.date_key === dk)
    return { dk, netMs, isOff, isFuture, hasLogs }
  })

  // ── Summary metrics ──────────────────────────────────────────

  $: weekTotalMs = getLastNDays(7).reduce((s, dk) => s + dayNetMs(dk, $logs, now), 0)

  $: monthAvgMs = (() => {
    const worked = getCurrentMonthDays()
      .filter(dk => dk <= todayDk && $logs.some(l => l.date_key === dk))
    if (worked.length === 0) return 0
    return worked.reduce((s, dk) => s + dayNetMs(dk, $logs, now), 0) / worked.length
  })()

  $: missedDays = getCurrentMonthDays()
    .filter(dk => dk <= todayDk)
    .filter(dk => !isOffDay(dk, $offDays, $dayOverrides) && !$logs.some(l => l.date_key === dk))
    .length

  $: streak = (() => {
    const minMs = $minimumDailyHours * 3_600_000
    let count = 0
    for (let i = 0; i < 365; i++) {
      const d = new Date(now)
      d.setDate(now.getDate() - i)
      const dk = dateKey(d)
      if (isOffDay(dk, $offDays, $dayOverrides)) continue
      const net = dayNetMs(dk, $logs, now)
      if (net >= minMs) {
        count++
      } else if (dk === todayDk && !$logs.some(l => l.date_key === dk)) {
        continue // today not yet started — don't break streak
      } else {
        break
      }
    }
    return count
  })()

  $: cumOtMs = sparkPts.at(-1) ?? 0

  // ── Platform split ───────────────────────────────────────────

  $: platformSplit = (() => {
    const days = new Set(chartDays)
    const ml = $logs.filter(l => days.has(l.date_key) && l.date_key <= todayDk)
    const officeMs = computeNetMs(ml.filter(l => l.platform === 'office').sort(byTs))
    const homeMs   = computeNetMs(ml.filter(l => l.platform === 'home').sort(byTs))
    const total = officeMs + homeMs
    return {
      officeMs, homeMs, total,
      officePct: total > 0 ? officeMs / total : 0,
      homePct:   total > 0 ? homeMs   / total : 0,
    }
  })()

  // ── Per-day platform breakdown ───────────────────────────────

  $: platformDayData = chartDays.map(dk => {
    const dayLogs  = $logs.filter(l => l.date_key === dk)
    const isFuture = dk > todayDk

    const offLogs  = dayLogs.filter(l => l.platform === 'office').sort(byTs)
    const homeLogs = dayLogs.filter(l => l.platform === 'home').sort(byTs)
    const offOpen  = offLogs.length  > 0 && offLogs.at(-1).action  === 'resume'
    const homeOpen = homeLogs.length > 0 && homeLogs.at(-1).action === 'resume'
    const isToday  = dk === todayDk

    const officeMs = computeNetMs(offLogs,  offOpen  && isToday ? now : null)
    const homeMs   = computeNetMs(homeLogs, homeOpen && isToday ? now : null)
    return { dk, officeMs, homeMs, isFuture, hasLogs: dayLogs.length > 0 }
  })

  $: maxPlatMs  = Math.max(3_600_000, ...platformDayData.map(d => d.officeMs + d.homeMs))
  $: maxPlatHrs = Math.ceil(maxPlatMs / 3_600_000)
  $: pGap = IW / Math.max(1, platformDayData.length)
  $: pW   = Math.max(2, pGap * 0.65)

  function pX(i)    { return PL + i * pGap + (pGap - pW) / 2 }
  function pHms(ms) { return Math.max(0, Math.min(1, ms / maxPlatMs) * IH) }

  // Rectangle with rounded top corners only (for topmost bar segment)
  function roundedTopRect(x, y, w, h, r = 3) {
    if (h <= 0 || w <= 0) return ''
    const cr = Math.min(r, w / 2, h)
    return `M ${x},${y + cr} Q ${x},${y} ${x + cr},${y} L ${x + w - cr},${y} Q ${x + w},${y} ${x + w},${y + cr} L ${x + w},${y + h} L ${x},${y + h} Z`
  }

  $: platYTicks = [
    { y: PT + IH,       label: '0' },
    { y: PT + IH * 0.5, label: `${Math.round(maxPlatHrs / 2)}h` },
    { y: PT,            label: `${maxPlatHrs}h` },
  ]

  function showPlatLabel(i) {
    if (period === 'week') return true
    const n = platformDayData.length
    if (n <= 15) return true
    return i === 0 || (i + 1) % 5 === 0 || i === n - 1
  }

  // ── SVG bar chart ────────────────────────────────────────────

  const CW = 400, CH = 180
  const PL = 36, PR = 8, PT = 12, PB = 28
  const IW = CW - PL - PR
  const IH = CH - PT - PB

  $: maxHrs  = Math.max($requiredHours + 2, 12)
  $: maxMs_  = maxHrs * 3_600_000
  $: bGap    = IW / Math.max(1, dayData.length)
  $: bW      = Math.max(2, bGap * 0.65)

  function bX(i) { return PL + i * bGap + (bGap - bW) / 2 }
  function bYtop(ms) { return PT + IH - Math.min(1, ms / maxMs_) * IH }
  function bH(ms)    { return Math.max(0, Math.min(1, ms / maxMs_) * IH) }

  function barFill(day) {
    if (day.isFuture || !day.hasLogs) return 'var(--color-border)'
    const minMs = $minimumDailyHours * 3_600_000
    const reqMs = $requiredHours * 3_600_000
    if (day.netMs < minMs) return 'var(--color-ot-neg)'
    if (day.netMs >= reqMs) return 'var(--color-ot-pos)'
    return 'var(--color-primary)'
  }

  $: targetY = PT + IH - ($requiredHours / maxHrs) * IH

  $: yTicks = [
    { y: PT + IH,       label: '0' },
    { y: PT + IH * 0.5, label: `${Math.round(maxHrs / 2)}h` },
    { y: PT,            label: `${maxHrs}h` },
  ]

  function xLabel(dk) {
    const d = new Date(dk + 'T12:00:00')
    return period === 'week'
      ? ['Su','Mo','Tu','We','Th','Fr','Sa'][d.getDay()]
      : String(d.getDate())
  }

  function showXLabel(i) {
    if (period === 'week') return true
    if (chartDays.length <= 15) return true
    return i === 0 || (i + 1) % 5 === 0 || i === chartDays.length - 1
  }

  // ── Sparkline (cumulative OT) ────────────────────────────────

  $: sparkPts = (() => {
    const reqMs = $requiredHours * 3_600_000
    const pts = []
    let cum = 0
    for (const dk of chartDays) {
      if (dk > todayDk) break
      const dayLogs = $logs.filter(l => l.date_key === dk).sort(byTs)
      if (dayLogs.length > 0) {
        const isOpen = dayLogs.at(-1).action === 'resume'
        const netMs  = computeNetMs(dayLogs, isOpen && dk === todayDk ? now : null)
        cum += isOffDay(dk, $offDays, $dayOverrides) ? netMs : netMs - reqMs
      }
      pts.push(cum)
    }
    return pts
  })()

  $: spMin   = sparkPts.length > 0 ? Math.min(0, ...sparkPts) : 0
  $: spMax   = sparkPts.length > 0 ? Math.max(0, ...sparkPts) : 3_600_000
  $: spRange = Math.max(spMax - spMin, 3_600_000)

  // Full-width OT chart helpers (reuse CW/CH/PL/PR/PT/PB/IW/IH from bar chart)
  $: otZeroY = PT + IH - ((0 - spMin) / spRange) * IH

  $: otPath = sparkPts.length > 0
    ? 'M ' + sparkPts.map((v, i) => {
        const x = sparkPts.length > 1 ? PL + (i / (sparkPts.length - 1)) * IW : PL + IW / 2
        const y = PT + IH - ((v - spMin) / spRange) * IH
        return `${x.toFixed(1)},${y.toFixed(1)}`
      }).join(' L ')
    : ''

  $: otAreaPath = otPath
    ? `${otPath} L ${(PL + IW).toFixed(1)},${otZeroY.toFixed(1)} L ${PL.toFixed(1)},${otZeroY.toFixed(1)} Z`
    : ''

  $: otYTicks = (() => {
    if (sparkPts.length === 0) return []
    const ticks = [{ y: otZeroY, label: '0' }]
    if (spMax > 0) ticks.push({ y: PT, label: fmtDuration(spMax, true) })
    if (spMin < 0) ticks.push({ y: PT + IH, label: fmtDuration(spMin, true) })
    return ticks
  })()

  // ── Avg hours by day of week ─────────────────────────────────

  const DOW_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

  $: weekdayAvg = (() => {
    const minMs = $minimumDailyHours * 3_600_000
    const reqMs = $requiredHours * 3_600_000
    const buckets = Array.from({ length: 7 }, () => ({ totalMs: 0, count: 0 }))
    const allDks = [...new Set($logs.map(l => l.date_key))].sort()
    for (const dk of allDks) {
      if (dk > todayDk) continue
      if (isOffDay(dk, $offDays, $dayOverrides)) continue
      const dayLogs = $logs.filter(l => l.date_key === dk).sort(byTs)
      const isOpen  = dayLogs.at(-1)?.action === 'resume'
      const netMs   = computeNetMs(dayLogs, isOpen && dk === todayDk ? now : null)
      if (netMs > 0) {
        const dow = new Date(dk + 'T12:00:00').getDay()
        buckets[dow].totalMs += netMs
        buckets[dow].count++
      }
    }
    return DOW_NAMES.map((name, dow) => {
      const { totalMs, count } = buckets[dow]
      const avgMs  = count > 0 ? totalMs / count : 0
      const enough = count >= 3
      const isOff  = $offDays.includes(dow)
      let fill = 'var(--color-border)'
      if (avgMs > 0) {
        if (!enough)          fill = 'var(--color-primary)'   // faded via opacity
        else if (avgMs < minMs) fill = 'var(--color-ot-neg)'
        else if (avgMs >= reqMs) fill = 'var(--color-ot-pos)'
        else                   fill = 'var(--color-primary)'
      }
      return { name, dow, avgMs, count, isOff, enough, fill }
    })
  })()

  const WN = 7  // always 7 bars
  $: wGap = IW / WN
  $: wW   = Math.max(4, wGap * 0.65)
  $: wMaxHrs = Math.max($requiredHours + 2, 12)
  $: wMaxMs  = wMaxHrs * 3_600_000
  $: wTargetY = PT + IH - ($requiredHours / wMaxHrs) * IH
  $: wYTicks  = [
    { y: PT + IH,       label: '0' },
    { y: PT + IH * 0.5, label: `${Math.round(wMaxHrs / 2)}h` },
    { y: PT,            label: `${wMaxHrs}h` },
  ]

  function wX(i)      { return PL + i * wGap + (wGap - wW) / 2 }
  function wBYtop(ms) { return PT + IH - Math.min(1, ms / wMaxMs) * IH }
  function wBH(ms)    { return Math.max(0, Math.min(1, ms / wMaxMs) * IH) }
</script>

<main class="analytics">

  <!-- Period toggle -->
  <div class="period-toggle">
    <button class="period-btn" class:active={period === 'week'}  on:click={() => period = 'week'}>Week</button>
    <button class="period-btn" class:active={period === 'month'} on:click={() => period = 'month'}>Month</button>
  </div>

  <!-- Summary metrics -->
  <div class="summary-cards">
    <div class="card metric-card">
      <div class="metric-label">This week</div>
      <div class="metric-value tabnum">{fmtDuration(weekTotalMs)}</div>
    </div>
    <div class="card metric-card">
      <div class="metric-label">Daily avg</div>
      <div class="metric-value tabnum">{fmtDuration(monthAvgMs)}</div>
      <div class="metric-sub">this month</div>
    </div>
    <div class="card metric-card">
      <div class="metric-label">Streak</div>
      <div class="metric-value streak-val tabnum">{streak}</div>
      <div class="metric-sub">days</div>
    </div>
    <div class="card metric-card">
      <div class="metric-label">Missed</div>
      <div class="metric-value tabnum" class:missed-bad={missedDays > 0} class:missed-ok={missedDays === 0}>{missedDays}</div>
      <div class="metric-sub">days this month</div>
    </div>
  </div>

  <!-- 2×2 charts grid -->
  <div class="charts-grid">

  <!-- Bar chart -->
  <div class="card">
    <div class="section-title">{period === 'week' ? 'Last 7 days' : 'This month'}</div>
    <svg class="chart-svg" viewBox="0 0 {CW} {CH}">
      <!-- Y gridlines + labels -->
      {#each yTicks as tick}
        <line
          x1={PL} y1={tick.y} x2={CW - PR} y2={tick.y}
          style="stroke: var(--color-border)" stroke-width="1"
        />
        <text x={PL - 4} y={tick.y + 4} text-anchor="end" font-size="9" style="fill: var(--color-text-muted)">{tick.label}</text>
      {/each}

      <!-- Required-hours target line -->
      <line
        x1={PL} y1={targetY} x2={CW - PR} y2={targetY}
        style="stroke: var(--color-primary)" stroke-width="1.5" stroke-dasharray="5,4" opacity="0.5"
      />

      <!-- Bars -->
      {#each dayData as day, i}
        {#if day.hasLogs || !day.isFuture}
          <rect
            x={bX(i)} y={bYtop(day.netMs)}
            width={bW} height={bH(day.netMs)}
            rx="2"
            style="fill: {barFill(day)}"
          />
        {/if}
        <!-- Empty-day placeholder bar (1px) -->
        {#if !day.hasLogs && !day.isFuture}
          <rect
            x={bX(i)} y={PT + IH - 1}
            width={bW} height="1"
            style="fill: var(--color-border)"
          />
        {/if}
      {/each}

      <!-- X axis labels -->
      {#each chartDays as dk, i}
        {#if showXLabel(i)}
          <text
            x={bX(i) + bW / 2} y={CH - 6}
            text-anchor="middle" font-size="9"
            font-weight={dk === todayDk ? '700' : '400'}
            style="fill: {dk === todayDk ? 'var(--color-primary)' : 'var(--color-text-muted)'}"
          >{xLabel(dk)}</text>
        {/if}
      {/each}
    </svg>

    <div class="legend">
      <span class="legend-item"><span class="legend-dot" style="background: var(--color-ot-pos)"></span>≥ required</span>
      <span class="legend-item"><span class="legend-dot" style="background: var(--color-primary)"></span>partial</span>
      <span class="legend-item"><span class="legend-dot" style="background: var(--color-ot-neg)"></span>under min</span>
    </div>
  </div>

  <!-- Cumulative OT balance -->
  <div class="card">
    <div class="section-title">OT Balance · {period === 'week' ? 'Last 7 days' : monthName()}</div>

    {#if otPath}
      <svg class="chart-svg" viewBox="0 0 {CW} {CH}">
        <defs>
          <!-- Clip to above-zero area (positive OT) -->
          <clipPath id="ot-clip-pos">
            <rect x={PL} y={PT} width={IW} height={Math.max(0, otZeroY - PT)} />
          </clipPath>
          <!-- Clip to below-zero area (negative OT) -->
          <clipPath id="ot-clip-neg">
            <rect x={PL} y={otZeroY} width={IW} height={Math.max(0, PT + IH - otZeroY)} />
          </clipPath>
        </defs>

        <!-- Y gridlines + labels -->
        {#each otYTicks as tick}
          <line x1={PL} y1={tick.y} x2={CW - PR} y2={tick.y}
            style="stroke: {tick.label === '0' ? 'var(--color-text-muted)' : 'var(--color-border)'}"
            stroke-width={tick.label === '0' ? 1.5 : 1}
            stroke-dasharray={tick.label === '0' ? '' : '3,3'}
          />
          <text x={PL - 4} y={tick.y + 4} text-anchor="end" font-size="9"
            style="fill: var(--color-text-muted)">{tick.label}</text>
        {/each}

        <!-- Positive area fill (above zero) -->
        <path d={otAreaPath} clip-path="url(#ot-clip-pos)"
          style="fill: var(--color-ot-pos-subtle)" />
        <!-- Negative area fill (below zero) -->
        <path d={otAreaPath} clip-path="url(#ot-clip-neg)"
          style="fill: var(--color-ot-neg-subtle)" />

        <!-- Line -->
        <path d={otPath} fill="none" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"
          style="stroke: {cumOtMs >= 0 ? 'var(--color-ot-pos)' : 'var(--color-ot-neg)'}" />

        <!-- X axis labels -->
        {#each sparkPts as _, i}
          {#if showXLabel(i)}
            {@const x = sparkPts.length > 1 ? PL + (i / (sparkPts.length - 1)) * IW : PL + IW / 2}
            {@const dk = chartDays[i]}
            <text x={x.toFixed(1)} y={CH - 6} text-anchor="middle" font-size="9"
              font-weight={dk === todayDk ? '700' : '400'}
              style="fill: {dk === todayDk ? 'var(--color-primary)' : 'var(--color-text-muted)'}"
            >{xLabel(dk)}</text>
          {/if}
        {/each}
      </svg>
    {/if}

    <div class="ot-total">
      <div class="ot-value tabnum" class:positive={cumOtMs >= 0} class:negative={cumOtMs < 0}>
        {fmtDuration(cumOtMs, true)}
      </div>
      <div class="metric-sub">total {period === 'week' ? 'this week' : 'this month'}</div>
    </div>
  </div>

  <!-- Avg hours by day of week (all historical data) -->
  <div class="card">
    <div class="section-title">Avg hours by weekday · all time</div>
    <svg class="chart-svg" viewBox="0 0 {CW} {CH}">
      <!-- Y gridlines + labels -->
      {#each wYTicks as tick}
        <line x1={PL} y1={tick.y} x2={CW - PR} y2={tick.y}
          style="stroke: var(--color-border)" stroke-width="1" />
        <text x={PL - 4} y={tick.y + 4} text-anchor="end" font-size="9"
          style="fill: var(--color-text-muted)">{tick.label}</text>
      {/each}
      <line x1={PL} y1={wTargetY} x2={CW - PR} y2={wTargetY}
        style="stroke: var(--color-primary)" stroke-width="1.5" stroke-dasharray="5,4" opacity="0.5" />
      {#each weekdayAvg as day, i}
        {#if day.avgMs > 0}
          <path d={roundedTopRect(wX(i), wBYtop(day.avgMs), wW, wBH(day.avgMs))}
            opacity={day.enough ? 1 : 0.35} style="fill: {day.fill}" />
          <text x={wX(i) + wW / 2} y={wBYtop(day.avgMs) - 3}
            text-anchor="middle" font-size="8" style="fill: var(--color-text-muted)">{day.count}×</text>
        {:else}
          <rect x={wX(i)} y={PT + IH - 1} width={wW} height="1" style="fill: var(--color-border)" />
        {/if}
        <text x={wX(i) + wW / 2} y={CH - 6} text-anchor="middle" font-size="9"
          font-weight={day.isOff ? '400' : '500'}
          style="fill: {day.isOff ? 'var(--color-border)' : 'var(--color-text-muted)'}"
        >{day.name}</text>
      {/each}
    </svg>
    <div class="avg-note">Faded bar = fewer than 3 logged days on that weekday</div>
  </div>

  <!-- Platform distribution across month -->
  {#if platformSplit.total > 0}
    <div class="card">
      <div class="section-title">Platform distribution · {period === 'week' ? 'Last 7 days' : monthName()}</div>

      <!-- Stacked bar chart: office + home per day -->
      <svg class="chart-svg" viewBox="0 0 {CW} {CH}">
        <!-- Y gridlines + labels -->
        {#each platYTicks as tick}
          <line x1={PL} y1={tick.y} x2={CW - PR} y2={tick.y}
            style="stroke: var(--color-border)" stroke-width="1" />
          <text x={PL - 4} y={tick.y + 4} text-anchor="end" font-size="9"
            style="fill: var(--color-text-muted)">{tick.label}</text>
        {/each}

        <!-- Stacked bars -->
        {#each platformDayData as day, i}
          {#if !day.isFuture}
            <!-- Office segment (bottom) — sharp corners when home sits on top, rounded top when alone -->
            {#if day.officeMs > 0}
              {#if day.homeMs > 0}
                <rect x={pX(i)} y={PT + IH - pHms(day.officeMs)}
                  width={pW} height={pHms(day.officeMs)}
                  style="fill: var(--color-office)" />
              {:else}
                <path d={roundedTopRect(pX(i), PT + IH - pHms(day.officeMs), pW, pHms(day.officeMs))}
                  style="fill: var(--color-office)" />
              {/if}
            {/if}
            <!-- Home segment (always topmost) — rounded top only -->
            {#if day.homeMs > 0}
              <path d={roundedTopRect(pX(i), PT + IH - pHms(day.officeMs) - pHms(day.homeMs), pW, pHms(day.homeMs))}
                style="fill: var(--color-home)" />
            {/if}
            <!-- Empty-day placeholder -->
            {#if !day.hasLogs}
              <rect x={pX(i)} y={PT + IH - 1} width={pW} height="1"
                style="fill: var(--color-border)" />
            {/if}
          {/if}
        {/each}

        <!-- X axis labels -->
        {#each platformDayData as day, i}
          {#if showPlatLabel(i)}
            <text
              x={pX(i) + pW / 2} y={CH - 6}
              text-anchor="middle" font-size="9"
              font-weight={day.dk === todayDk ? '700' : '400'}
              style="fill: {day.dk === todayDk ? 'var(--color-primary)' : 'var(--color-text-muted)'}"
            >{xLabel(day.dk)}</text>
          {/if}
        {/each}
      </svg>

      <!-- Monthly totals summary -->
      <div class="split-summary">
        <div class="split-bar-wrap">
          <div class="split-bar">
            {#if platformSplit.officePct > 0}
              <div class="split-seg split-office" style="width: {(platformSplit.officePct * 100).toFixed(1)}%"></div>
            {/if}
            {#if platformSplit.homePct > 0}
              <div class="split-seg split-home" style="width: {(platformSplit.homePct * 100).toFixed(1)}%"></div>
            {/if}
          </div>
        </div>
        <div class="split-labels">
          <span class="split-label">
            <span class="split-dot" style="background: var(--color-office)"></span>
            Office — {fmtDuration(platformSplit.officeMs)} ({(platformSplit.officePct * 100).toFixed(0)}%)
          </span>
          <span class="split-label">
            <span class="split-dot" style="background: var(--color-home)"></span>
            Home — {fmtDuration(platformSplit.homeMs)} ({(platformSplit.homePct * 100).toFixed(0)}%)
          </span>
        </div>
      </div>
    </div>
  {/if}

  </div> <!-- end charts-grid -->

</main>

<style>
  .analytics {
    max-width: 1000px;
    margin: 0 auto;
    padding: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  /* ── Charts 2×2 grid ── */
  .charts-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-4);
  }
  @media (max-width: 640px) {
    .charts-grid { grid-template-columns: 1fr; }
  }

  /* ── Period toggle ── */
  .period-toggle {
    display: flex;
    background: var(--color-surface-2);
    border-radius: var(--radius-md);
    padding: 3px;
    gap: 2px;
  }
  .period-btn {
    flex: 1;
    padding: var(--space-2) var(--space-4);
    border-radius: calc(var(--radius-md) - 3px);
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text-muted);
    transition: background var(--transition), color var(--transition), box-shadow var(--transition);
  }
  .period-btn.active {
    background: var(--color-surface);
    color: var(--color-primary);
    font-weight: 600;
    box-shadow: var(--shadow-sm);
  }

  /* ── Summary cards grid (4-up) ── */
  .summary-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-3);
  }
  @media (max-width: 540px) {
    .summary-cards { grid-template-columns: repeat(2, 1fr); }
  }

  /* ── Metric cards ── */
  .metric-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: var(--space-1);
    padding: var(--space-4) var(--space-3);
    margin-top: 0;
  }
  .metric-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--color-text-muted);
  }
  .metric-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--color-text);
    line-height: 1;
  }
  .streak-val  { color: var(--color-primary); }
  .missed-bad  { color: var(--color-ot-neg); }
  .missed-ok   { color: var(--color-ot-pos); }
  .metric-sub {
    font-size: 0.7rem;
    color: var(--color-text-muted);
  }

  /* ── Bar chart ── */
  .chart-svg {
    display: block;
    width: 100%;
    height: auto;
    overflow: visible;
    margin-top: var(--space-3);
  }
  .legend {
    display: flex;
    gap: var(--space-4);
    justify-content: center;
    margin-top: var(--space-3);
    flex-wrap: wrap;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    font-size: 0.72rem;
    color: var(--color-text-muted);
  }
  .legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* ── OT balance card ── */
  .ot-total {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }
  .ot-value {
    font-size: 1.5rem;
    font-weight: 700;
    line-height: 1;
  }
  .ot-value.positive { color: var(--color-ot-pos); }
  .ot-value.negative { color: var(--color-ot-neg); }

  /* ── Platform split ── */
  .split-summary { margin-top: var(--space-4); }
  .split-bar-wrap { margin-top: var(--space-2); }
  .split-bar {
    display: flex;
    height: 10px;
    border-radius: 5px;
    overflow: hidden;
    background: var(--color-surface-2);
  }
  .split-seg { height: 100%; transition: width var(--transition); }
  .split-office { background: var(--color-office); }
  .split-home   { background: var(--color-home); }
  .split-labels {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }
  .split-label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 0.8125rem;
    color: var(--color-text-muted);
  }
  .split-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* ── Weekday avg chart ── */
  .avg-note {
    margin-top: var(--space-3);
    font-size: 0.72rem;
    color: var(--color-text-muted);
    text-align: center;
  }
</style>
