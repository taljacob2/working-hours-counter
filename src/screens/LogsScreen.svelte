<script>
  import { onDestroy } from 'svelte'
  import { user, logs, selectedDate, calCursor, logResolution, editingLogId, selectedDayLogs, showToast } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'
  import { fmtDuration, dateKey, computeNetMs, computeTotalMs, byTs,
           loggedDaysInMonth, monthBounds, monthCumulativeOtMs, isOffDay } from '../lib/timeUtils.js'
  import { requiredHours, minimumDailyHours, maximumDailyHours, commuteGapMinutes, use24HourFormat, offDays, dayOverrides, rebalHistoryCap } from '../stores/appStore.js'

  // Live clock for open-ended spans
  let now = new Date()
  const ticker = setInterval(() => now = new Date(), 1000)
  onDestroy(() => clearInterval(ticker))

  const todayKey = dateKey()
  let filterUnderMin = false
  let filterAboveMax = false
  let filterOpenSession = false
  let filterUnopenSession = false

  // ── Calendar helpers ─────────────────────────────────────────
  const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

  $: calYear  = $calCursor.getFullYear()
  $: calMonth = $calCursor.getMonth() + 1

  // Historical log simulation for view mode: undo rebalances from newest down to targetIdx
  function computeHistoricalLogs(currentLogs, history, targetIdx) {
    let simLogs = [...currentLogs]
    for (let i = history.length - 1; i >= targetIdx; i--) {
      const { inserted_ids, updated, deleted_logs } = history[i].delta
      simLogs = simLogs.filter(l => !inserted_ids.includes(l.id))
      for (const u of updated)
        simLogs = simLogs.map(l => l.id === u.id ? { ...l, timestamp: u.old_timestamp, date_key: u.old_date_key } : l)
      simLogs = [...simLogs, ...deleted_logs]
    }
    return simLogs
  }

  $: effectiveLogs = viewingEntryIdx === null
    ? $logs
    : computeHistoricalLogs($logs, monthHistory, viewingEntryIdx)

  $: calDays = buildCalendar(calYear, calMonth, effectiveLogs, $offDays, $dayOverrides, $requiredHours, $minimumDailyHours, $maximumDailyHours, now)
  $: cumOt   = monthCumulativeOtMs(effectiveLogs, calYear, calMonth, $requiredHours, $offDays, $dayOverrides)
  $: daysLogged = loggedDaysInMonth(effectiveLogs, calYear, calMonth).length

  function buildCalendar(year, month, logsArr, offDaysArr, dayOverridesObj, reqHours, minHours, maxHours, currentTime) {
    const first = new Date(year, month - 1, 1)
    const last  = new Date(year, month, 0)
    const cells = []
    // Leading empties
    for (let i = 0; i < first.getDay(); i++) cells.push(null)
    for (let d = 1; d <= last.getDate(); d++) {
      const key = `${year}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`
      const dl  = logsArr.filter(l => l.date_key === key).sort(byTs)
      const isOpen = dl.length > 0 && dl.at(-1).action === 'resume'
      const netMs  = computeNetMs(dl, (isOpen && key === todayKey) ? currentTime : null)
      const reqMs  = reqHours * 3_600_000
      const minMs  = minHours * 3_600_000
      const dayIsOff = isOffDay(key, offDaysArr, dayOverridesObj)
      const hasOverride = dayOverridesObj[key] != null
      const otMs   = dl.length > 0 ? (dayIsOff ? netMs : netMs - reqMs) : null
      const offMs  = computeNetMs(dl.filter(l => l.platform === 'office'), (isOpen && key === todayKey) ? currentTime : null)
      const homeMs = computeNetMs(dl.filter(l => l.platform === 'home'),   (isOpen && key === todayKey) ? currentTime : null)
      const underMin = !dayIsOff && netMs > 0 && netMs < minMs
      const aboveMax = !dayIsOff && netMs > maxHours * 3_600_000
      let hasUnopenSession = false
      let openCount = 0
      for (const l of dl) {
        if (l.action === 'resume') openCount++
        else if (l.action === 'pause') {
          if (openCount === 0) { hasUnopenSession = true; break }
          openCount--
        }
      }
      cells.push({ d, key, count: dl.length, netMs, otMs, offMs, homeMs, underMin, aboveMax, isOff: dayIsOff, hasOverride, isOpen, hasUnopenSession })
    }
    return cells
  }

  function prevMonth() { calCursor.update(c => new Date(c.getFullYear(), c.getMonth() - 1, 1)) }
  function nextMonth() { calCursor.update(c => new Date(c.getFullYear(), c.getMonth() + 1, 1)) }
  function goToday()   { calCursor.set(new Date(new Date().getFullYear(), new Date().getMonth(), 1)); selectedDate.set(todayKey) }

  function toLocalISO(date) {
    const d = new Date(date)
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  }

  // ── Edit state ───────────────────────────────────────────────
  let editForm = null

  function startEdit(log) {
    editingLogId.set(log.id)
    editForm = {
      id:         log.id,
      timestamp:  toLocalISO(log.timestamp),
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
      timestamp:  toLocalISO(d),
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
  // In view mode use the simulated logs for the selected day; otherwise use the live store
  $: viewDayLogs = viewingEntryIdx === null
    ? $selectedDayLogs
    : effectiveLogs.filter(l => l.date_key === $selectedDate).sort(byTs)

  $: selNetMs    = computeNetMs(viewDayLogs, ($selectedDate === todayKey && viewingEntryIdx === null) ? now : null)
  $: selDayIsOff = isOffDay($selectedDate, $offDays, $dayOverrides)
  $: selOtMs     = viewDayLogs.length > 0 ? (selDayIsOff ? selNetMs : selNetMs - $requiredHours * 3_600_000) : null

  // ── Format helpers ───────────────────────────────────────────
  function fmtTs(ts) {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: !$use24HourFormat })
  }
  function fmtDate(ts) {
    return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
  }

  const MONTH_NAMES = ['January','February','March','April','May','June',
    'July','August','September','October','November','December']

  // ── Rebalancing ──────────────────────────────────────────────
  let showRebalancing = false
  let monthHistory = []
  let historyLoading = false
  let viewingEntryIdx = null  // null = current, 0 = before any rebalance, N = after N rebalances
  let _histMonthKey = null    // last month key for which history was loaded

  // ── OT ceiling (optional "cut" on top of the normal rebalance) ─
  let otCutEnabled = false
  let otCutCeilingMs = null   // target ceiling in ms; null = not yet initialised for this cumOt

  // Keep the ceiling valid as cumOt changes (month nav, or after an apply) — only ever
  // clamp down/initialise, never fight the user's own drag.
  $: if (showRebalancing && (otCutCeilingMs == null || otCutCeilingMs > cumOt)) otCutCeilingMs = Math.max(0, cumOt)

  function fmtKeyShort(key) {
    return new Date(key + 'T12:00:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
  }

  // How many ms of new home sessions can actually fit in a day's evening + morning slots.
  // Mirrors computeHumanHoursBlocks slot logic without the neededMs cap.
  function computeExcessOtSlotCapacity(sortedLogs, dateStr, commuteGapMins) {
    const commuteMs = commuteGapMins * 60_000
    const dayStart  = new Date(dateStr + 'T06:00:00').getTime()
    const dayEnd    = new Date(dateStr + 'T22:00:00').getTime()
    let eveningStart = new Date(dateStr + 'T17:00:00').getTime()
    if (sortedLogs.length > 0) {
      const last = sortedLogs[sortedLogs.length - 1]
      eveningStart = last.platform === 'office'
        ? new Date(last.timestamp).getTime() + commuteMs
        : new Date(last.timestamp).getTime() + 60_000
    }
    let morningEnd = new Date(dateStr + 'T09:00:00').getTime()
    if (sortedLogs.length > 0) {
      const first = sortedLogs[0]
      const firstTs = new Date(first.timestamp).getTime()
      morningEnd = (first.platform === 'home' && first.action === 'resume')
        ? firstTs
        : (first.platform === 'office' ? firstTs - commuteMs : firstTs - 60_000)
    }
    return Math.max(0, dayEnd - eveningStart) + Math.max(0, morningEnd - dayStart)
  }

  function suggestRebalancing(cells, minMs, maxMs, reqMs, offDays = [], dayOverrides = {}, logs = [], commuteGapMins = 45) {
    const dayIsOff = key => isOffDay(key, offDays, dayOverrides)

    // Mutable working copies — only logged days matter
    const days = cells
      .filter(c => c !== null && c.count > 0)
      .map(c => ({ key: c.key, currentMs: c.netMs, offMs: c.offMs, isOff: dayIsOff(c.key) }))

    // Days that have at least one home-platform log — only these can be trimmed as donors
    const daysWithHomeLogs = new Set(logs.filter(l => l.platform === 'home').map(l => l.date_key))

    // Days with an open (unpaused) session — excluded from being recipients because their
    // netMs changes every second, making the rebalancing plan unstable while they're active
    const openSessionDays = new Set()
    for (const dk of [...new Set(logs.map(l => l.date_key))]) {
      const dl = logs.filter(l => l.date_key === dk).sort(byTs)
      if (dl.at(-1)?.action === 'resume') openSessionDays.add(dk)
    }

    const transfers = []

    // Pass 1: off-day home hours → working days.
    // Priority 1: fill under-required days first. Priority 2: fill under-max days.
    // Off days go first so their surplus is never crowded out by working-day OT donors.
    for (const donor of days.filter(d => d.isOff && d.currentMs > d.offMs && daysWithHomeLogs.has(d.key)).sort((a, b) => b.currentMs - a.currentMs)) {
      const floor = donor.offMs
      while (donor.currentMs > floor) {
        const underReq = days
          .filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < reqMs && !openSessionDays.has(d.key))
          .sort((a, b) => a.currentMs - b.currentMs)[0]
        const underMax = !underReq && days
          .filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < maxMs && !openSessionDays.has(d.key))
          .sort((a, b) => a.currentMs - b.currentMs)[0]
        const rec = underReq || underMax
        if (!rec) break
        const available = donor.currentMs - floor
        const needed    = (rec.currentMs < reqMs ? reqMs : maxMs) - rec.currentMs
        if (needed <= 0) break
        const transfer  = Math.min(available, needed)
        donor.currentMs -= transfer
        rec.currentMs   += transfer
        transfers.push({ from: donor.key, to: rec.key, ms: transfer })
      }
    }

    // Pass 2: fix remaining working-day deficits (under-required ← above-max / OT donors).
    const recipients = days
      .filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < reqMs && !openSessionDays.has(d.key))
      .sort((a, b) => a.currentMs - b.currentMs)

    for (const rec of recipients) {
      while (rec.currentMs < reqMs) {
        const aboveMaxDonors = days
          .filter(d => !d.tappedOut && !d.isOff && d.currentMs > maxMs && daysWithHomeLogs.has(d.key))
          .sort((a, b) => b.currentMs - a.currentMs)
        const otDonors = days
          .filter(d => !d.tappedOut && !d.isOff && d.currentMs > reqMs && d.currentMs <= maxMs && daysWithHomeLogs.has(d.key))
          .sort((a, b) => b.currentMs - a.currentMs)

        const donor = aboveMaxDonors[0] || otDonors[0]
        if (!donor) break

        let floor = donor.currentMs > maxMs ? maxMs : reqMs
        floor = Math.max(floor, donor.offMs)

        const available = donor.currentMs - floor
        if (available <= 0) { donor.tappedOut = true; continue }

        const needed   = reqMs - rec.currentMs
        const transfer = Math.min(available, needed)
        donor.currentMs -= transfer
        rec.currentMs   += transfer
        transfers.push({ from: donor.key, to: rec.key, ms: transfer })
      }
    }

    // Pass 3: remaining above-max excess → working days below max (distributed as extra OT).
    // Cap each recipient by its real scheduling capacity (evening + morning slots) so we
    // never over-trim donors relative to what can actually be absorbed.
    for (const d of days) d.tappedOut3 = false
    const pass3Recipients = days
      .filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < maxMs && !openSessionDays.has(d.key))
      .sort((a, b) => a.currentMs - b.currentMs)

    for (const rec of pass3Recipients) {
      const recLogs   = logs.filter(l => l.date_key === rec.key).sort(byTs)
      const slotCap   = computeExcessOtSlotCapacity(recLogs, rec.key, commuteGapMins)
      const maxForRec = Math.min(slotCap, maxMs - rec.currentMs)
      if (maxForRec <= 0) continue
      let given = 0
      while (given < maxForRec) {
        const donor = days
          .filter(d => !d.isOff && !d.tappedOut3 && d.currentMs > maxMs && daysWithHomeLogs.has(d.key))
          .sort((a, b) => b.currentMs - a.currentMs)[0]
        if (!donor) break
        const floor    = Math.max(maxMs, donor.offMs)
        const available = donor.currentMs - floor
        if (available <= 0) { donor.tappedOut3 = true; continue }
        const needed   = maxForRec - given
        const transfer = Math.min(available, needed)
        donor.currentMs -= transfer
        rec.currentMs   += transfer
        given           += transfer
        transfers.push({ from: donor.key, to: rec.key, ms: transfer, isExcessOt: true })
      }
    }

    // Off days are never violations — only check non-off days
    const stillUnderMin = days.filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < minMs).map(d => d.key)
    const stillAboveMax = days.filter(d => !d.isOff && d.currentMs > maxMs).map(d => d.key)
    const noViolations  = stillUnderMin.length === 0 && stillAboveMax.length === 0

    // Keys that received excess-OT transfers (Pass 3) — shown distinctly in the panel
    const excessOtRecipients = new Set(transfers.filter(t => t.isExcessOt).map(t => t.to))

    return { transfers, stillUnderMin, stillAboveMax, noViolations, excessOtRecipients }
  }

  $: rebalancing = (showRebalancing && viewingEntryIdx === null)
    ? suggestRebalancing(
        calDays.filter(Boolean),
        $minimumDailyHours * 3_600_000,
        $maximumDailyHours * 3_600_000,
        $requiredHours    * 3_600_000,
        $offDays,
        $dayOverrides,
        effectiveLogs,
        $commuteGapMinutes
      )
    : null

  // Per-cell delta map from the normal donor→recipient rebalance alone (no OT cut).
  $: baseRebalMap = (() => {
    if (!rebalancing) return {}
    const map = {}
    for (const t of rebalancing.transfers) {
      map[t.from] = (map[t.from] ?? 0) - t.ms
      map[t.to]   = (map[t.to]   ?? 0) + t.ms
    }
    return map
  })()

  // How much OT to actually cut this round, given the user's chosen ceiling.
  $: otCutAmountMs = (otCutEnabled && otCutCeilingMs != null) ? Math.max(0, cumOt - otCutCeilingMs) : 0

  // Max ms a single day can actually give up in one shot, per computeDaySuggestion's own
  // rules (it only ever shrinks/deletes ONE home session per apply). netMs - reqMs is just
  // the day's theoretical OT — a lot of that can be office-sourced (never touched) or split
  // across sessions too small to fully satisfy a big ask, so this simulates the real cap
  // rather than trusting the theoretical number.
  function achievableCutForDay(dk, netMs, reqMs, maxMs, commuteGapMins) {
    const theoretical = netMs - reqMs
    if (theoretical <= 0) return 0
    const dayLogs = effectiveLogs.filter(l => l.date_key === dk).sort(byTs)
    if (!dayLogs.length) return 0
    const synthetic = { stillAboveMax: [], excessOtRecipients: new Set() }
    const sugg = computeDaySuggestion(dayLogs, dk, synthetic, { [dk]: -theoretical }, maxMs, commuteGapMins, netMs)
    return Math.abs(sugg ? simulateSuggestionDeltaMs(dayLogs, sugg) : 0)
  }

  // Per-cell ms to remove on top of baseRebalMap to bring cumulative OT down toward the
  // chosen ceiling. Uses water-filling: find the common "water level" of remaining OT such
  // that trimming every donor above it down to that level adds up to the requested cut.
  // Largest-OT days give up the most, everyone touched lands at the same remaining OT, and
  // days already below the level are left untouched — reads as ordinary daily variance
  // rather than one day being conspicuously hollowed out.
  $: cutMap = (() => {
    if (!rebalancing || otCutAmountMs <= 0) return {}
    const reqMs = $requiredHours * 3_600_000
    const maxMs = $maximumDailyHours * 3_600_000
    const daysWithHomeLogs = new Set(effectiveLogs.filter(l => l.platform === 'home').map(l => l.date_key))

    const donors = calDays
      .filter(c => c && c.count > 0 && !isOffDay(c.key, $offDays, $dayOverrides) && daysWithHomeLogs.has(c.key))
      .filter(c => !rebalancing.stillAboveMax.includes(c.key)) // deltaMs there is fixed regardless of rebalMap
      .filter(c => (baseRebalMap[c.key] ?? 0) >= 0) // skip days already donating in the normal rebalance — keeps the achievability check below unambiguous
      .map(c => {
        const theoreticalAvail = Math.max(0, c.netMs - reqMs)
        if (theoreticalAvail <= 0) return { key: c.key, avail: 0 }
        const achievable = achievableCutForDay(c.key, c.netMs, reqMs, maxMs, $commuteGapMinutes)
        return { key: c.key, avail: Math.min(theoreticalAvail, achievable) }
      })
      .filter(d => d.avail > 0)

    if (!donors.length) return {}
    const totalAvail = donors.reduce((s, d) => s + d.avail, 0)
    const target = Math.min(otCutAmountMs, totalAvail)
    if (target <= 0) return {}

    // Binary search the water level L where sum(max(0, avail_i - L)) == target.
    let lo = 0, hi = Math.max(...donors.map(d => d.avail))
    for (let i = 0; i < 60; i++) {
      const mid = (lo + hi) / 2
      const sum = donors.reduce((s, d) => s + Math.max(0, d.avail - mid), 0)
      if (sum > target) lo = mid; else hi = mid
    }
    const level = hi

    const map = {}
    for (const d of donors) {
      const cut = Math.round(Math.max(0, d.avail - level))
      if (cut > 0) map[d.key] = -cut
    }
    return map
  })()

  // Total OT the cut can realistically achieve, given real per-day session capacity —
  // may be less than otCutAmountMs if home-loggable time can't cover the full request.
  $: otCutAchievableMs = Object.values(cutMap).reduce((s, v) => s - v, 0)

  // Final per-cell delta map: normal rebalance + OT cut layered on top.
  $: rebalMap = (() => {
    const map = { ...baseRebalMap }
    for (const [k, v] of Object.entries(cutMap)) map[k] = (map[k] ?? 0) + v
    return map
  })()

  $: hasAdjustments = !!rebalancing && (rebalancing.transfers.length > 0 || Object.keys(cutMap).length > 0)

  // Per-day summary for the redesigned panel
  $: rebalSummary = (() => {
    if (!rebalancing || !Object.keys(rebalMap).length) return { donors: [], recipients: [] }
    const donors = [], recipients = []
    for (const [key, deltaMs] of Object.entries(rebalMap)) {
      const cell = calDays.find(c => c && c.key === key)
      if (!cell) continue
      // isExcessOt = this day received Pass-3 excess-OT hours (may also have received normal hours)
      const isExcessOt = rebalancing.excessOtRecipients.has(key)
      const isOtCut = cutMap[key] != null
      const entry = { key, originalMs: cell.netMs, newMs: cell.netMs + deltaMs, deltaMs, isExcessOt, isOtCut }
      if (deltaMs < 0) donors.push(entry)
      else             recipients.push(entry)
    }
    donors.sort((a, b) => a.deltaMs - b.deltaMs)
    recipients.sort((a, b) => b.deltaMs - a.deltaMs)
    return { donors, recipients }
  })()

  // Adjusted rebalMap where recipient targets are capped to what donors can actually deliver.
  // Prevents phantom OT when a donor day has no trimmable home session.
  $: effectiveRebalMap = (() => {
    if (!rebalancing) return rebalMap
    const maxMs = $maximumDailyHours * 3_600_000
    // Simulate each NORMAL donor (not an OT-cut-only donor — that ms is being removed, not
    // redistributed, so it must never inflate what recipients are allowed to draw) to measure
    // actually-achievable ms reduction.
    let achievable = 0
    for (const [dk, v] of Object.entries(baseRebalMap)) {
      if (v >= 0) continue
      const dayLogs = effectiveLogs.filter(l => l.date_key === dk).sort(byTs)
      if (!dayLogs.length) continue
      const netMs = computeNetMs(dayLogs)
      const sugg = computeDaySuggestion(dayLogs, dk, rebalancing, baseRebalMap, maxMs, $commuteGapMinutes, netMs)
      achievable += Math.abs(sugg ? simulateSuggestionDeltaMs(dayLogs, sugg) : 0)
    }
    // Cap each recipient to at most what donors can actually deliver
    const m = { ...rebalMap }
    let rem = achievable
    for (const [dk, v] of Object.entries(m).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])) {
      m[dk] = Math.min(v, rem)
      rem = Math.max(0, rem - m[dk])
    }
    return m
  })()

  // Returns the net ms change in worked hours that a suggestion would produce
  function simulateSuggestionDeltaMs(dayLogs, sugg) {
    if (!sugg) return 0
    if (sugg.type === 'create_blocks')     return sugg.totalDeltaMs
    if (sugg.type === 'delete_session')    return -sugg.sessionDurationMs
    if (sugg.type === 'create_block_logs') return new Date(sugg.pauseTs).getTime() - new Date(sugg.resumeTs).getTime()
    if (sugg.type === 'create_log')        return sugg.deltaMs
    if (sugg.logId) {
      const modified = dayLogs.map(l => l.id === sugg.logId ? { ...l, timestamp: sugg.newTs } : l)
      return computeNetMs(modified.sort(byTs)) - computeNetMs(dayLogs)
    }
    return 0
  }

  // Projected OT after all suggestions are applied, with per-day breakdown
  $: otProjection = (() => {
    if (!rebalancing || !showRebalancing) return null
    const maxMs = $maximumDailyHours * 3_600_000
    const affectedKeys = new Set([...Object.keys(rebalMap), ...(rebalancing.stillAboveMax || [])])
    const breakdown = []
    let totalDelta = 0
    for (const dk of [...affectedKeys]) {
      const dayLogs = effectiveLogs.filter(l => l.date_key === dk).sort(byTs)
      if (!dayLogs.length) continue
      const netMs = computeNetMs(dayLogs)
      const sugg = computeDaySuggestion(dayLogs, dk, rebalancing, effectiveRebalMap, maxMs, $commuteGapMinutes, netMs)
      const delta = sugg ? simulateSuggestionDeltaMs(dayLogs, sugg) : 0
      const dayCell = calDays.find(c => c?.key === dk)
      const currentOt = dayCell?.otMs ?? 0
      const isDonor    = (rebalMap[dk] ?? 0) < 0
      const isExcessOt = !isDonor && (rebalancing.excessOtRecipients?.has(dk) ?? false)
      const isOtCut    = cutMap[dk] != null
      const noSuggestion = !sugg || delta === 0
      breakdown.push({ dk, isDonor, isExcessOt, isOtCut, currentOt, projectedOt: currentOt + delta, delta, noSuggestion })
      totalDelta += delta
    }
    if (!breakdown.length) return null
    // donors first, then excess-OT recipients, then regular recipients
    breakdown.sort((a, b) => {
      const rank = r => r.isDonor ? 0 : r.isExcessOt ? 1 : 2
      return rank(a) - rank(b)
    })
    // Donor loss that's attributable to a deliberate OT cut is excluded here — that ms is
    // meant to vanish, not be matched by a recipient, so it must never show up as "unplaced".
    const donorLoss = breakdown.filter(r => r.isDonor).reduce((s, r) => {
      const cutPortion = Math.abs(cutMap[r.dk] ?? 0)
      return s + Math.max(0, Math.abs(r.delta) - cutPortion)
    }, 0)
    const recipientGain = breakdown.filter(r => !r.isDonor).reduce((s, r) => s + Math.max(0, r.delta), 0)
    const unplacedMs   = Math.max(0, donorLoss - recipientGain)
    return { projectedOt: cumOt + totalDelta, delta: totalDelta, breakdown, unplacedMs }
  })()

  function computeHumanHoursBlocks(sortedLogs, neededMs, dateStr, commuteGapMins) {
    const commuteMs = commuteGapMins * 60_000
    const dayStart  = new Date(dateStr + 'T06:00:00').getTime()
    const dayEnd    = new Date(dateStr + 'T22:00:00').getTime()

    // Evening slot: after last log (+ commute gap if office, else 1 min)
    let eveningStart = new Date(dateStr + 'T17:00:00').getTime()
    if (sortedLogs.length > 0) {
      const last   = sortedLogs[sortedLogs.length - 1]
      const lastTs = new Date(last.timestamp).getTime()
      eveningStart = last.platform === 'office' ? lastTs + commuteMs : lastTs + 60_000
    }
    const eveningCap = Math.max(0, dayEnd - eveningStart)

    // Morning slot: before first log
    // If first log is a home resume, extend it backward instead of creating a new block
    let morningEnd = new Date(dateStr + 'T09:00:00').getTime()
    let morningFirstHomeResume = null
    if (sortedLogs.length > 0) {
      const first   = sortedLogs[0]
      const firstTs = new Date(first.timestamp).getTime()
      if (first.platform === 'home' && first.action === 'resume') {
        morningEnd = firstTs
        morningFirstHomeResume = first
      } else {
        morningEnd = first.platform === 'office' ? firstTs - commuteMs : firstTs - 60_000
      }
    }
    const morningCap = Math.max(0, morningEnd - dayStart)

    const blocks = []
    let remaining = neededMs

    if (eveningCap > 0 && remaining > 0) {
      const take = Math.min(eveningCap, remaining)
      blocks.push({
        kind:       'new_block',
        resumeTs:   new Date(eveningStart).toISOString(),
        pauseTs:    new Date(eveningStart + take).toISOString(),
        durationMs: take
      })
      remaining -= take
    }

    if (morningCap > 0 && remaining > 0) {
      const take = Math.min(morningCap, remaining)
      if (morningFirstHomeResume) {
        blocks.push({
          kind:       'extend_resume',
          logId:      morningFirstHomeResume.id,
          originalTs: morningFirstHomeResume.timestamp,
          newTs:      new Date(morningEnd - take).toISOString(),
          durationMs: take
        })
      } else {
        blocks.push({
          kind:       'new_block',
          resumeTs:   new Date(morningEnd - take).toISOString(),
          pauseTs:    new Date(morningEnd).toISOString(),
          durationMs: take
        })
      }
      remaining -= take
    }

    return { type: 'create_blocks', blocks, totalDeltaMs: neededMs - remaining, isPartial: remaining > 0 }
  }

  // Pure per-day suggestion function — called by the reactive and by applyAllRebalance
  function computeDaySuggestion(sortedDayLogs, dateStr, rebalancing, rebalMap, maxMs, commuteGapMins, netMs) {
    if (!sortedDayLogs.length) return null

    const isStillAboveMax = rebalancing?.stillAboveMax?.includes(dateStr) ?? false

    let deltaMs
    if (isStillAboveMax) {
      deltaMs = -(Math.max(0, netMs - maxMs))
      if (deltaMs === 0) return null
    } else if (rebalMap[dateStr] != null) {
      deltaMs = rebalMap[dateStr]
      if (deltaMs === 0) return null
    } else {
      return null
    }

    const logsCopy = sortedDayLogs

    const isExcessOtRec = !isStillAboveMax &&
      (rebalancing?.excessOtRecipients?.has(dateStr) ?? false)
    if (isExcessOtRec && deltaMs > 0) {
      return computeHumanHoursBlocks(logsCopy, deltaMs, dateStr, commuteGapMins)
    }

    let openHomeResume = null
    for (const l of logsCopy) {
      if (l.platform === 'home') {
        if (l.action === 'resume') openHomeResume = l
        else if (l.action === 'pause') openHomeResume = null
      }
    }

    if (deltaMs > 0 && openHomeResume) {
      const curTs = new Date(openHomeResume.timestamp).getTime()
      let limitTs = new Date(dateStr + 'T23:59:59').getTime()
      const nextOffice = logsCopy.find(l => l.timestamp > openHomeResume.timestamp && l.platform === 'office')
      if (nextOffice) limitTs = new Date(nextOffice.timestamp).getTime() - (commuteGapMins * 60_000)
      const inc = Math.min(deltaMs, limitTs - curTs)
      if (inc > 0) return { type: 'create_log', action: 'pause', newTs: new Date(curTs + inc).toISOString(), deltaMs: inc, isPartial: inc < deltaMs }
    }

    const getBenefit = (oldTs, newTs) => {
      const getDist = dt => { const c = new Date(dt); c.setHours(13, 30, 0, 0); return Math.abs(dt.getTime() - c.getTime()) }
      return getDist(new Date(oldTs)) - getDist(new Date(newTs))
    }

    if (deltaMs < 0) {
      const needed = -deltaMs
      const candidates = []
      for (let i = 0; i < logsCopy.length; i++) {
        const log = logsCopy[i]
        if (log.platform !== 'home') continue
        if (log.action === 'pause') {
          const prev = logsCopy[i - 1]
          if (prev?.action === 'resume' && prev.platform === 'home') {
            const sessionMs = new Date(log.timestamp) - new Date(prev.timestamp)
            if (sessionMs > 0) {
              if (needed >= sessionMs) {
                candidates.push({ isDeleteSession: true, resumeLogId: prev.id, pauseLogId: log.id, sessionDurationMs: sessionMs, appliedRed: sessionMs, isPartial: needed > sessionMs })
              } else {
                const newTsIso = new Date(new Date(log.timestamp).getTime() - needed).toISOString()
                candidates.push({ logId: log.id, originalTs: log.timestamp, newTs: newTsIso, deltaMs: needed, isPartial: false, appliedRed: needed, benefit: getBenefit(log.timestamp, newTsIso) })
              }
            }
          }
        } else if (log.action === 'resume') {
          const next = logsCopy[i + 1]
          if (next?.action === 'pause' && next.platform === 'home') {
            const sessionMs = new Date(next.timestamp) - new Date(log.timestamp)
            if (sessionMs > 0) {
              if (needed >= sessionMs) {
                candidates.push({ isDeleteSession: true, resumeLogId: log.id, pauseLogId: next.id, sessionDurationMs: sessionMs, appliedRed: sessionMs, isPartial: needed > sessionMs })
              } else {
                const newTsIso = new Date(new Date(log.timestamp).getTime() + needed).toISOString()
                candidates.push({ logId: log.id, originalTs: log.timestamp, newTs: newTsIso, deltaMs: needed, isPartial: false, appliedRed: needed, benefit: getBenefit(log.timestamp, newTsIso) })
              }
            }
          }
        }
      }
      if (candidates.length > 0) {
        candidates.sort((a, b) => b.appliedRed !== a.appliedRed ? b.appliedRed - a.appliedRed : (b.benefit ?? 0) - (a.benefit ?? 0))
        const best = candidates[0]
        if (best.isDeleteSession) return { type: 'delete_session', resumeLogId: best.resumeLogId, pauseLogId: best.pauseLogId, sessionDurationMs: best.sessionDurationMs, isPartial: best.isPartial }
        return { logId: best.logId, originalTs: best.originalTs, newTs: best.newTs, deltaMs: best.deltaMs, isPartial: best.isPartial }
      }
    } else {
      const needed = deltaMs
      const candidates = []
      for (let i = 0; i < logsCopy.length; i++) {
        const log = logsCopy[i]
        if (log.platform !== 'home') continue
        if (log.action === 'pause') {
          const next = logsCopy[i + 1]
          const curTs = new Date(log.timestamp).getTime()
          let limitTs = new Date(log.timestamp.slice(0, 10) + 'T23:59:59').getTime()
          if (next) { limitTs = new Date(next.timestamp).getTime(); if (next.platform === 'office') limitTs -= commuteGapMins * 60_000 }
          const inc = limitTs - curTs
          if (inc > 0) { const appliedInc = Math.min(inc, needed); const newTsIso = new Date(curTs + appliedInc).toISOString(); candidates.push({ logId: log.id, originalTs: log.timestamp, newTs: newTsIso, deltaMs: needed, isPartial: appliedInc < needed, appliedInc, benefit: getBenefit(log.timestamp, newTsIso) }) }
        } else if (log.action === 'resume') {
          const prev = logsCopy[i - 1]
          const curTs = new Date(log.timestamp).getTime()
          let limitTs = new Date(log.timestamp.slice(0, 10) + 'T06:00:00').getTime()
          if (prev) { limitTs = new Date(prev.timestamp).getTime(); if (prev.platform === 'office') limitTs += commuteGapMins * 60_000 }
          const inc = curTs - limitTs
          if (inc > 0) { const appliedInc = Math.min(inc, needed); const newTsIso = new Date(curTs - appliedInc).toISOString(); candidates.push({ logId: log.id, originalTs: log.timestamp, newTs: newTsIso, deltaMs: needed, isPartial: appliedInc < needed, appliedInc, benefit: getBenefit(log.timestamp, newTsIso) }) }
        }
      }
      if (candidates.length > 0) {
        candidates.sort((a, b) => b.appliedInc !== a.appliedInc ? b.appliedInc - a.appliedInc : b.benefit - a.benefit)
        const best = candidates[0]
        return { logId: best.logId, originalTs: best.originalTs, newTs: best.newTs, deltaMs: best.deltaMs, isPartial: best.isPartial }
      }
    }

    if (deltaMs > 0) {
      const lastLog = logsCopy[logsCopy.length - 1]
      let startTs = new Date(dateStr + 'T17:00:00').getTime()
      if (lastLog) { startTs = new Date(lastLog.timestamp).getTime(); startTs += lastLog.platform === 'office' ? commuteGapMins * 60_000 : 60_000 }
      const limitTs = new Date(dateStr + 'T23:59:59').getTime()
      let endTs = Math.min(startTs + deltaMs, limitTs)
      return { type: 'create_block_logs', resumeTs: new Date(startTs).toISOString(), pauseTs: new Date(endTs).toISOString(), deltaMs: endTs - startTs, isPartial: startTs + deltaMs > limitTs }
    }

    const homeLogs = logsCopy.filter(l => l.platform === 'home')
    if (!homeLogs.length) return null
    const last = homeLogs[homeLogs.length - 1]
    const adj = last.action === 'pause' ? deltaMs : -deltaMs
    return { logId: last.id, originalTs: last.timestamp, newTs: new Date(new Date(last.timestamp).getTime() + adj).toISOString(), deltaMs: adj, isPartial: false }
  }

  // Per-day log adjustment suggestion (thin reactive wrapper) — disabled in view mode
  $: logAdjustmentSuggestion = (showRebalancing && viewingEntryIdx === null && viewDayLogs.length > 0)
    ? computeDaySuggestion([...viewDayLogs].sort(byTs), $selectedDate, rebalancing, effectiveRebalMap, $maximumDailyHours * 3_600_000, $commuteGapMinutes, selNetMs)
    : null

  // Unified sorted table rows: existing logs interleaved with suggestion rows
  $: tableRows = (() => {
    const sugg = logAdjustmentSuggestion
    const rows = []

    // Build lookup maps from the current suggestion
    const extendResumeMap = {}  // logId → { newTs, durationMs }
    const deleteSessionSet = new Set()

    if (sugg?.type === 'create_blocks') {
      for (const block of sugg.blocks) {
        if (block.kind === 'extend_resume') extendResumeMap[block.logId] = block
      }
    } else if (sugg?.type === 'delete_session') {
      deleteSessionSet.add(sugg.resumeLogId)
      deleteSessionSet.add(sugg.pauseLogId)
    }

    // Existing log rows
    for (const log of [...viewDayLogs].sort(byTs)) {
      rows.push({
        kind:          'log',
        log,
        isSugg:        sugg?.logId === log.id,
        extendSugg:    extendResumeMap[log.id] ?? null,
        isDeleteSugg:  deleteSessionSet.has(log.id),
        ts:            new Date(log.timestamp).getTime()
      })
    }

    // New-log suggestion (single pause for an open session): shown inline in table
    if (sugg?.type === 'create_log') {
      rows.push({ kind: 'new_log', ts: new Date(sugg.newTs).getTime() })
    }
    // create_blocks / create_block_logs new sessions are shown as a suggestion card above the table

    rows.sort((a, b) => a.ts - b.ts)

    return rows
  })()

  // ── Day overrides (per-date work/off toggle) ─────────────────
  async function setDayOverride(dk, type) {
    const updated = { ...$dayOverrides, [dk]: type }
    dayOverrides.set(updated)
    localStorage.setItem('whl_day_overrides', JSON.stringify(updated))
    const sb = getSupabase()
    const { error } = await sb.from('work_settings').upsert([{ key: 'dayOverrides', value: JSON.stringify(updated) }])
    if (error) showToast('Failed to save day override', 'error')
    else showToast(type === 'off' ? 'Marked as off day' : 'Marked as work day', 'success')
  }

  async function removeDayOverride(dk) {
    const updated = { ...$dayOverrides }
    delete updated[dk]
    dayOverrides.set(updated)
    localStorage.setItem('whl_day_overrides', JSON.stringify(updated))
    const sb = getSupabase()
    const { error } = await sb.from('work_settings').upsert([{ key: 'dayOverrides', value: JSON.stringify(updated) }])
    if (error) showToast('Failed to remove day override', 'error')
    else showToast('Reverted to default', 'info')
  }

  async function applyCreateLog(action, newTs) {
    isSaving = true
    const sb = getSupabase()
    const payload = {
      id: crypto.randomUUID(),
      timestamp: newTs,
      platform: 'home',
      action,
      date_key: $selectedDate
    }
    const { data, error } = await sb.from('work_logs').insert(payload).select().single()
    isSaving = false
    if (error) { showToast('Error creating log: ' + error.message, 'error'); return }
    logs.update(ls => [...ls, data])
    showToast(`Rebalance ${action} log created`, 'success')
  }

  async function applyBlock(block) {
    isSaving = true
    const sb = getSupabase()
    const base = { platform: 'home', date_key: $selectedDate }
    const { data: rd, error: re } = await sb.from('work_logs')
      .insert({ ...base, id: crypto.randomUUID(), action: 'resume', timestamp: block.resumeTs }).select().single()
    if (re) { showToast('Error: ' + re.message, 'error'); isSaving = false; return }
    const { data: pd, error: pe } = await sb.from('work_logs')
      .insert({ ...base, id: crypto.randomUUID(), action: 'pause', timestamp: block.pauseTs }).select().single()
    if (pe) { showToast('Error: ' + pe.message, 'error'); isSaving = false; return }
    logs.update(ls => [...ls, rd, pd])
    showToast('Rebalance block applied', 'success')
    isSaving = false
  }

  async function applyExtendResume(logId, newTs) {
    isSaving = true
    const sb = getSupabase()
    const payload = { timestamp: newTs, date_key: newTs.slice(0, 10) }
    const { error } = await sb.from('work_logs').update(payload).eq('id', logId)
    isSaving = false
    if (error) { showToast('Update failed: ' + error.message, 'error'); return }
    logs.update(ls => ls.map(l => l.id === logId ? { ...l, ...payload } : l))
    showToast('Home session extended for rebalancing', 'success')
  }

  async function deleteSession(resumeLogId, pauseLogId) {
    isSaving = true
    const sb = getSupabase()
    const { error } = await sb.from('work_logs').delete().in('id', [resumeLogId, pauseLogId])
    isSaving = false
    if (error) { showToast('Delete failed: ' + error.message, 'error'); return }
    logs.update(ls => ls.filter(l => l.id !== resumeLogId && l.id !== pauseLogId))
    showToast('Session deleted', 'success')
  }

  // ── Rebalance history (Supabase-backed, per month) ──────────
  async function loadMonthHistory() {
    const mk = `${calYear}-${String(calMonth).padStart(2, '0')}`
    if (_histMonthKey === mk) return
    _histMonthKey = mk
    viewingEntryIdx = null
    historyLoading = true
    const sb = getSupabase()
    const { data, error } = await sb
      .from('rebalance_history')
      .select('*')
      .eq('user_id', $user.id)
      .eq('month_key', mk)
      .order('applied_at', { ascending: true })
    historyLoading = false
    if (error) { showToast('Failed to load rebalance history', 'error'); return }
    monthHistory = data || []
  }

  // Load/reload history when the panel opens or the month changes while it's open
  $: if (showRebalancing) {
    const _mk = `${calYear}-${String(calMonth).padStart(2, '0')}`
    if (_histMonthKey !== _mk) loadMonthHistory()
  }

  async function applyAllRebalance() {
    if (!rebalancing || !showRebalancing || viewingEntryIdx !== null) return
    const maxMs = $maximumDailyHours * 3_600_000
    const commuteGapMins = $commuteGapMinutes
    const otBefore = cumOt

    const affectedKeys = new Set([...Object.keys(rebalMap), ...(rebalancing.stillAboveMax || [])])
    const currentLogs = $logs  // freeze for suggestion computation

    const updates = []          // { logId, newTs }
    const inserts = []          // raw log payloads
    const deletes = []          // log IDs to delete
    const deltaUpdated = []     // { id, old_timestamp, old_date_key }
    const deltaDeletedLogs = [] // full log objects that will be deleted

    for (const dk of [...affectedKeys]) {
      const dayLogs = currentLogs.filter(l => l.date_key === dk).sort(byTs)
      if (!dayLogs.length) continue
      const netMs = computeNetMs(dayLogs)
      const sugg = computeDaySuggestion(dayLogs, dk, rebalancing, effectiveRebalMap, maxMs, commuteGapMins, netMs)
      if (!sugg) continue

      const base = { platform: 'home', date_key: dk }
      if (sugg.type === 'delete_session') {
        deletes.push(sugg.resumeLogId, sugg.pauseLogId)
        deltaDeletedLogs.push(...currentLogs.filter(l => l.id === sugg.resumeLogId || l.id === sugg.pauseLogId))
      } else if (sugg.type === 'create_blocks') {
        for (const block of sugg.blocks) {
          if (block.kind === 'new_block') {
            inserts.push({ ...base, id: crypto.randomUUID(), action: 'resume', timestamp: block.resumeTs })
            inserts.push({ ...base, id: crypto.randomUUID(), action: 'pause',  timestamp: block.pauseTs  })
          } else if (block.kind === 'extend_resume') {
            updates.push({ logId: block.logId, newTs: block.newTs })
            const old = currentLogs.find(l => l.id === block.logId)
            if (old) deltaUpdated.push({ id: block.logId, old_timestamp: old.timestamp, old_date_key: old.date_key })
          }
        }
      } else if (sugg.type === 'create_block_logs') {
        inserts.push({ ...base, id: crypto.randomUUID(), action: 'resume', timestamp: sugg.resumeTs })
        inserts.push({ ...base, id: crypto.randomUUID(), action: 'pause',  timestamp: sugg.pauseTs  })
      } else if (sugg.type === 'create_log') {
        inserts.push({ ...base, id: crypto.randomUUID(), action: sugg.action, timestamp: sugg.newTs })
      } else if (sugg.logId) {
        updates.push({ logId: sugg.logId, newTs: sugg.newTs })
        const old = currentLogs.find(l => l.id === sugg.logId)
        if (old) deltaUpdated.push({ id: sugg.logId, old_timestamp: old.timestamp, old_date_key: old.date_key })
      }
    }

    isSaving = true
    const sb = getSupabase()

    for (const { logId, newTs } of updates) {
      const { error } = await sb.from('work_logs').update({ timestamp: newTs, date_key: newTs.slice(0, 10) }).eq('id', logId)
      if (error) { showToast('Apply failed: ' + error.message, 'error'); isSaving = false; return }
    }

    let insertedRows = []
    if (inserts.length) {
      const { data, error } = await sb.from('work_logs').insert(inserts).select()
      if (error) { showToast('Apply failed: ' + error.message, 'error'); isSaving = false; return }
      insertedRows = data || []
    }

    if (deletes.length) {
      const { error } = await sb.from('work_logs').delete().in('id', deletes)
      if (error) { showToast('Apply failed: ' + error.message, 'error'); isSaving = false; return }
    }

    let newLogs = $logs.filter(l => !deletes.includes(l.id))
    for (const { logId, newTs } of updates)
      newLogs = newLogs.map(l => l.id === logId ? { ...l, timestamp: newTs, date_key: newTs.slice(0, 10) } : l)
    newLogs = [...newLogs, ...insertedRows]
    logs.set(newLogs)

    const otAfter = monthCumulativeOtMs(newLogs, calYear, calMonth, $requiredHours, $offDays, $dayOverrides)

    // Save history entry to Supabase
    const monthKey = `${calYear}-${String(calMonth).padStart(2, '0')}`
    const delta = {
      inserted_ids: insertedRows.map(r => r.id),
      updated: deltaUpdated,
      deleted_logs: deltaDeletedLogs
    }
    const summary = {
      updates: updates.length, inserts: inserts.length, deletes: deletes.length,
      otBefore, otAfter, dateKeys: [...affectedKeys],
      otCutApplied: otCutEnabled && otCutAmountMs > 0,
      otCutCeilingMs: otCutEnabled ? otCutCeilingMs : null
    }
    const { data: histData, error: histErr } = await sb
      .from('rebalance_history')
      .insert({ user_id: $user.id, month_key: monthKey, delta, summary })
      .select().single()
    if (!histErr && histData) {
      let newHistory = [...monthHistory, histData]
      const cap = $rebalHistoryCap
      if (cap > 0 && newHistory.length > cap) {
        const toPrune = newHistory.slice(0, newHistory.length - cap)
        await sb.from('rebalance_history').delete().in('id', toPrune.map(e => e.id))
        newHistory = newHistory.slice(-cap)
      }
      monthHistory = newHistory
    }

    isSaving = false
    const otDelta = otAfter - otBefore
    const parts = []
    if (updates.length)  parts.push(`${updates.length} edited`)
    if (inserts.length)  parts.push(`${inserts.length} added`)
    if (deletes.length)  parts.push(`${deletes.length} deleted`)
    const otChange = otDelta === 0
      ? ''
      : ` · OT ${fmtDuration(otBefore, true)} → ${fmtDuration(otAfter, true)}`
    showToast(`Rebalancing applied (${parts.join(', ')})${otChange}`, 'success')
  }

  async function revertLatestRebalance() {
    const entry = monthHistory.at(-1)
    if (!entry) return
    const { inserted_ids, updated, deleted_logs } = entry.delta

    isSaving = true
    const sb = getSupabase()

    if (inserted_ids.length) {
      const { error } = await sb.from('work_logs').delete().in('id', inserted_ids)
      if (error) { showToast('Revert failed: ' + error.message, 'error'); isSaving = false; return }
    }
    for (const u of updated) {
      const { error } = await sb.from('work_logs').update({ timestamp: u.old_timestamp, date_key: u.old_date_key }).eq('id', u.id)
      if (error) { showToast('Revert failed: ' + error.message, 'error'); isSaving = false; return }
    }
    if (deleted_logs.length) {
      const { error } = await sb.from('work_logs').insert(deleted_logs)
      if (error) { showToast('Revert failed: ' + error.message, 'error'); isSaving = false; return }
    }

    const { error: delHistErr } = await sb.from('rebalance_history').delete().eq('id', entry.id)
    if (delHistErr) { showToast('Revert failed: ' + delHistErr.message, 'error'); isSaving = false; return }

    let newLogs = $logs.filter(l => !inserted_ids.includes(l.id))
    for (const u of updated)
      newLogs = newLogs.map(l => l.id === u.id ? { ...l, timestamp: u.old_timestamp, date_key: u.old_date_key } : l)
    newLogs = [...newLogs, ...deleted_logs]
    logs.set(newLogs)

    monthHistory = monthHistory.slice(0, -1)
    if (viewingEntryIdx !== null && viewingEntryIdx > monthHistory.length) viewingEntryIdx = null
    isSaving = false
    showToast('Rebalancing reverted', 'success')
  }

  async function applySuggestion() {
    if (!logAdjustmentSuggestion) return
    const sugg = logAdjustmentSuggestion

    const { logId, newTs } = sugg
    isSaving = true
    const sb = getSupabase()
    const payload = {
      timestamp: newTs,
      date_key: newTs.slice(0, 10),
    }
    const { error } = await sb.from('work_logs').update(payload).eq('id', logId)
    isSaving = false
    if (error) { showToast('Update failed: ' + error.message, 'error'); return }
    logs.update(ls => ls.map(l => l.id === logId ? { ...l, ...payload } : l))
    showToast('Log adjusted for rebalancing', 'success')
  }
</script>

<div class="logs-screen">
  <!-- LEFT: Calendar -->
  <aside class="cal-panel">

    {#if viewingEntryIdx !== null}
      <div class="view-mode-banner">
        <span>👁 {viewingEntryIdx === 0 ? 'Original state' : `After rebalance ${viewingEntryIdx} of ${monthHistory.length}`}</span>
        <button class="btn btn-sm btn-secondary" on:click={() => viewingEntryIdx = null}>✕ Exit</button>
      </div>
    {/if}

    <div class="cal-nav">
      <button class="btn btn-secondary btn-sm" on:click={prevMonth}>‹</button>
      <div class="cal-title">
        <strong>{MONTH_NAMES[calMonth-1]} {calYear}</strong>
      </div>
      <div class="cal-nav-right">
        <button class="btn btn-secondary btn-sm" on:click={goToday}>Today</button>
        <button class="btn btn-secondary btn-sm" on:click={nextMonth}>›</button>
      </div>
    </div>

    <div class="cal-meta">
      <div class="cal-stats">
        <span class="pill pill-muted">{daysLogged}d logged</span>
        <span class="pill {cumOt >= 0 ? 'pill-ot-pos' : 'pill-ot-neg'}">{fmtDuration(cumOt, true)} OT</span>
      </div>
      <button
        class="filter-btn {showRebalancing ? 'filter-btn--rebalance' : ''}"
        on:click={() => showRebalancing = !showRebalancing}
        title="Suggest how to redistribute hours to fix violations"
      >
        ⚖ Rebalance
      </button>
    </div>

    <div class="cal-filters">
      <button
        class="filter-btn {filterUnderMin ? 'filter-btn--neg' : ''}"
        on:click={() => filterUnderMin = !filterUnderMin}
        title="Show only days below the {$minimumDailyHours}h minimum"
      >
        ⚠ Under Min
      </button>
      <button
        class="filter-btn {filterAboveMax ? 'filter-btn--pos' : ''}"
        on:click={() => filterAboveMax = !filterAboveMax}
        title="Show only days above the {$maximumDailyHours}h maximum"
      >
        ⚠ Above Max
      </button>
      <button
        class="filter-btn {filterOpenSession ? 'filter-btn--live' : ''}"
        on:click={() => filterOpenSession = !filterOpenSession}
        title="Show only days with an unclosed (still-running) session"
      >
        ▶ Unclosed
      </button>
      <button
        class="filter-btn {filterUnopenSession ? 'filter-btn--warn' : ''}"
        on:click={() => filterUnopenSession = !filterUnopenSession}
        title="Show only days with a pause log that has no matching resume"
      >
        ⚠ Unopen
      </button>
    </div>

    <div class="cal-grid">
      {#each DAY_NAMES as dn}
        <div class="cal-day-name">{dn}</div>
      {/each}
      {#each calDays as cell}
        {#if cell === null}
          <div class="cal-cell cal-cell--empty"></div>
        {:else}
          {@const effectiveNet = (showRebalancing && rebalMap[cell.key] != null) ? cell.netMs + rebalMap[cell.key] : cell.netMs}
          {@const effectiveUnderMin = !cell.isOff && effectiveNet > 0 && effectiveNet < $minimumDailyHours * 3_600_000}
          {@const effectiveAboveMax = !cell.isOff && effectiveNet > $maximumDailyHours * 3_600_000}
          <button
            class="cal-cell"
            class:cal-cell--today={cell.key === todayKey}
            class:cal-cell--selected={cell.key === $selectedDate}
            class:cal-cell--off-day={cell.isOff}
            class:cal-cell--override={cell.hasOverride}
            class:cal-cell--ot-pos={cell.otMs !== null && cell.otMs >= 0}
            class:cal-cell--ot-neg={cell.otMs !== null && cell.otMs < 0}
            class:cal-cell--under-min={effectiveUnderMin}
            class:cal-cell--above-max={effectiveAboveMax}
            class:cal-cell--filtered-out={(filterUnderMin && !effectiveUnderMin) || (filterAboveMax && !effectiveAboveMax) || (filterOpenSession && !cell.isOpen) || (filterUnopenSession && !cell.hasUnopenSession)}
            class:cal-cell--open-session={cell.isOpen}
            class:cal-cell--unopen-session={cell.hasUnopenSession}
            class:cal-cell--rebal-donor={showRebalancing && rebalMap[cell.key] < 0}
            class:cal-cell--rebal-recipient={showRebalancing && rebalMap[cell.key] > 0}
            on:click={() => selectedDate.set(cell.key)}
          >
            <span class="cal-day-num">{cell.d}</span>
            {#if cell.count > 0}
              {#if showRebalancing && rebalMap[cell.key] != null}
                {@const delta  = rebalMap[cell.key]}
                {@const newNet = cell.netMs + delta}
                <span class="cal-net cal-net--orig tabnum">{fmtDuration(cell.netMs)}</span>
                <span class="cal-net cal-net--new tabnum">{fmtDuration(newNet)}</span>
                <span class="cal-delta tabnum {delta > 0 ? 'pos' : 'neg'}">{fmtDuration(delta, true)}</span>
              {:else}
                <span class="cal-net tabnum">{fmtDuration(cell.netMs)}</span>
                {#if cell.otMs !== null}
                  <span class="cal-ot tabnum {cell.otMs >= 0 ? 'pos' : 'neg'}">{fmtDuration(cell.otMs, true)}</span>
                {/if}
              {/if}
            {/if}
          </button>
        {/if}
      {/each}
    </div>

    {#if showRebalancing && (rebalancing || viewingEntryIdx !== null || monthHistory.length > 0)}
      <div class="rebal-panel">

        <!-- Header -->
        <div class="rebal-hd" style="flex-direction: column; align-items: flex-start; gap: 0.5rem;">
          <div style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span class="rebal-hd-icon">{viewingEntryIdx !== null ? '👁' : '⚖'}</span>
              <p class="rebal-hd-title" style="margin: 0; font-size: 1.1rem; font-weight: 600;">
                {#if viewingEntryIdx !== null}
                  {viewingEntryIdx === 0 ? 'Viewing: Original State' : `Viewing: After Rebalance ${viewingEntryIdx} of ${monthHistory.length}`}
                {:else}
                  Hour Redistribution Plan
                {/if}
              </p>
            </div>
            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
              {#if viewingEntryIdx !== null}
                <button class="btn btn-sm btn-secondary" style="font-size: 0.75rem;" on:click={() => viewingEntryIdx = null}>
                  ✕ Exit View
                </button>
              {:else if rebalancing}
                {#if rebalancing.noViolations}
                  <span class="badge badge-success">Balanced</span>
                {:else}
                  <span class="badge badge-warning">Action Required</span>
                {/if}
                {#if hasAdjustments}
                  <button class="btn btn-sm btn-primary" style="font-size: 0.75rem;" on:click={applyAllRebalance} disabled={isSaving}>
                    ⚡ Apply All
                  </button>
                {/if}
                {#if monthHistory.length > 0}
                  <button class="btn btn-sm btn-secondary" style="font-size: 0.75rem;" on:click={revertLatestRebalance} disabled={isSaving}>
                    ↩ Revert
                  </button>
                {/if}
              {/if}
            </div>
          </div>
          {#if rebalancing && !rebalancing.noViolations}
            <div class="rebal-violations">
              {#if rebalancing.stillAboveMax.length}
                <span class="rebal-violation-item rebal-violation--max">⚠ Still above {$maximumDailyHours}h: {rebalancing.stillAboveMax.map(fmtKeyShort).join(', ')}</span>
              {/if}
              {#if rebalancing.stillUnderMin.length}
                <span class="rebal-violation-item rebal-violation--min">⚠ Still under {$minimumDailyHours}h: {rebalancing.stillUnderMin.map(fmtKeyShort).join(', ')}</span>
              {/if}
            </div>
          {/if}
          {#if rebalancing && cumOt > 0}
            <div class="ot-cut-box">
              <label class="ot-cut-toggle">
                <input type="checkbox" bind:checked={otCutEnabled} />
                <span>✂ Cut reported OT to a lower ceiling</span>
              </label>
              {#if otCutEnabled}
                <div class="ot-cut-controls">
                  <input type="range" min="0" max={cumOt} step={15 * 60_000}
                    bind:value={otCutCeilingMs} class="ot-cut-slider" />
                  <span class="ot-cut-readout tabnum">Keep at most {fmtDuration(otCutCeilingMs ?? cumOt, true)}</span>
                </div>
                <p class="ot-cut-hint">
                  {#if otCutAmountMs > 0 && otCutAchievableMs > 0}
                    Will quietly trim {fmtDuration(otCutAchievableMs)} off the top — spread thin across your highest-OT days first, never below {$requiredHours}h on any day, so it still reads as ordinary day-to-day variance.
                    {#if otCutAchievableMs < otCutAmountMs - 60_000}
                      <strong>Only {fmtDuration(otCutAchievableMs)} of the requested {fmtDuration(otCutAmountMs)} can actually be trimmed</strong> — that's the most your logged home hours can supply in one pass. Projected OT will land around {fmtDuration(cumOt - otCutAchievableMs, true)}, above your {fmtDuration(otCutCeilingMs, true)} ceiling.
                    {/if}
                  {:else if otCutAmountMs > 0}
                    None of the requested cut can be trimmed — there's no eligible home-logged time to remove (office-tracked hours are never touched).
                  {:else}
                    Ceiling is at or above your current OT — nothing will be cut.
                  {/if}
                </p>
              {/if}
            </div>
          {/if}
          {#if rebalancing}
          <div class="ot-projection-box">
            <div class="ot-proj-row">
              <div class="ot-proj-col">
                <span class="ot-proj-label">Current OT</span>
                <strong class="ot-proj-val" style="color:{cumOt<0?'var(--color-ot-neg)':'var(--color-ot-pos)'};">{fmtDuration(cumOt,true)}</strong>
              </div>
              {#if otProjection}
                <span class="ot-proj-arrow">→</span>
                <div class="ot-proj-col">
                  <span class="ot-proj-label">After rebalance</span>
                  <strong class="ot-proj-val" style="color:{otProjection.projectedOt<0?'var(--color-ot-neg)':'var(--color-ot-pos)'};">{fmtDuration(otProjection.projectedOt,true)}</strong>
                </div>
                <span class="ot-proj-delta" style="color:{otProjection.delta<0?'var(--color-ot-neg)':'var(--color-ot-pos)'};">{fmtDuration(otProjection.delta,true)}</span>
              {/if}
            </div>
            {#if otProjection?.breakdown.length}
              <details class="ot-proj-breakdown">
                <summary>Why does OT change?</summary>
                <div class="ot-proj-steps">
                  <div class="ot-proj-step">
                    <span class="ot-proj-step-num">1</span>
                    <span>Days that logged <strong>more than {$maximumDailyHours}h</strong> have their home sessions shortened. The trimmed hours are moved to days that logged <strong>less than {$minimumDailyHours}h</strong> to bring them up to the minimum. OT is preserved in this exchange.</span>
                  </div>
                  <div class="ot-proj-step">
                    <span class="ot-proj-step-num">2</span>
                    <span>If over-limit days still have surplus after step 1, extra home sessions are added in the morning or evening of other working days — up to {$maximumDailyHours}h. OT is preserved here too, <em>unless</em> there is no free time slot available (morning and evening already occupied).</span>
                  </div>
                  {#if otProjection.unplacedMs > 0}
                    <div class="ot-proj-step ot-proj-step--warn">
                      <span class="ot-proj-step-num">3</span>
                      <span><strong>{fmtDuration(otProjection.unplacedMs)} could not be placed on any other day</strong> — every working day either already reached {$maximumDailyHours}h or had no free morning/evening slot. Those hours are trimmed with nowhere to go.{#if !(otCutEnabled && otCutAmountMs > 0)} <strong>This is the only reason OT decreases.</strong>{/if}</span>
                    </div>
                  {/if}
                  {#if otCutEnabled && otCutAmountMs > 0}
                    <div class="ot-proj-step ot-proj-step--warn">
                      <span class="ot-proj-step-num">{otProjection.unplacedMs > 0 ? '4' : '3'}</span>
                      <span>You've also chosen to cut up to <strong>{fmtDuration(otCutAmountMs)}</strong> down to a ceiling of <strong>{fmtDuration(otCutCeilingMs, true)}</strong> — spread across your highest-OT days, largest first, never below {$requiredHours}h on any day.</span>
                    </div>
                  {/if}
                </div>
                <table class="ot-proj-table">
                  <thead><tr><th>Day</th><th>What happens</th><th>OT now</th><th>OT after</th><th>&Delta;</th></tr></thead>
                  <tbody>
                    {#each otProjection.breakdown as row}
                      <tr>
                        <td>{fmtKeyShort(row.dk)}</td>
                        <td>
                          {#if row.isDonor && rebalancing.stillAboveMax.includes(row.dk)}
                            <span class="pill pill-ot-neg" style="font-size:0.68rem;">Hours trimmed (over {$maximumDailyHours}h)</span>
                          {:else if row.isDonor && row.noSuggestion}
                            <span class="pill pill-warn" style="font-size:0.68rem;">OT donated — no home logs to trim</span>
                          {:else if row.isDonor && row.isOtCut}
                            <span class="pill pill-ot-neg" style="font-size:0.68rem;">✂ OT cut</span>
                          {:else if row.isDonor}
                            <span class="pill pill-ot-neg" style="font-size:0.68rem;">OT donated</span>
                          {:else if row.isExcessOt}
                            <span class="pill pill-excess-ot" style="font-size:0.68rem;">Home sessions added (step 2)</span>
                          {:else}
                            <span class="pill pill-ot-pos" style="font-size:0.68rem;">Hours received (under {$minimumDailyHours}h)</span>
                          {/if}
                        </td>
                        <td style="color:{row.currentOt<0?'var(--color-ot-neg)':'var(--color-ot-pos)'};">{fmtDuration(row.currentOt,true)}</td>
                        <td style="color:{row.projectedOt<0?'var(--color-ot-neg)':'var(--color-ot-pos)'};">{fmtDuration(row.noSuggestion ? row.currentOt : row.projectedOt,true)}</td>
                        <td style="color:{row.delta<0?'var(--color-ot-neg)':'var(--color-ot-pos)'}; font-weight:700;">{row.noSuggestion ? '—' : fmtDuration(row.delta,true)}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
                <p class="ot-proj-note">Tip: days receiving hours in step 1 may show a smaller OT gain than expected — received hours first complete the {$requiredHours}h daily requirement before counting as OT.</p>
              </details>
            {/if}
          </div>
          <p class="rebal-hd-hint" style="margin: 0; font-size: 0.85rem;">Click any day below to view &amp; edit its logs &rarr;</p>
          {/if}
        </div>

        {#if rebalancing && !hasAdjustments}
          <div class="rebal-clean">
            <span class="rebal-clean-icon">&#10003;</span>
            <p>All logged days are already within {$minimumDailyHours}h–{$maximumDailyHours}h. Nothing to adjust.</p>
          </div>
        {:else if rebalancing}

          <!-- Donors -->
          {#if rebalSummary.donors.length}
            <div class="rebal-section">
              <p class="rebal-section-lbl rebal-lbl-donor">&#128228; Giving hours</p>
              {#each rebalSummary.donors as d}
                {@const donorExcessMs = Math.max(0, d.newMs - $maximumDailyHours * 3_600_000)}
                <button class="rebal-row rebal-row--donor"
                  on:click={() => selectedDate.set(d.key)}
                  title="View logs for {fmtKeyShort(d.key)}"
                >
                  <span class="rebal-day">{fmtKeyShort(d.key)}</span>
                  <div class="rebal-flow">
                    <span class="rebal-orig">{fmtDuration(d.originalMs)}</span>
                    <span class="rebal-arr">&rarr;</span>
                    <span class="rebal-new rebal-new--donor">{fmtDuration(d.newMs)}</span>
                    {#if donorExcessMs > 0}
                      <span class="rebal-arr">&rarr;</span>
                      <span class="rebal-new rebal-new--excess">{fmtDuration($maximumDailyHours * 3_600_000)} ✂</span>
                    {/if}
                  </div>
                  <span class="rebal-badge rebal-badge--donor">{fmtDuration(d.deltaMs, true)}</span>
                  {#if donorExcessMs > 0}
                    <span class="rebal-excess-tag">+{fmtDuration(donorExcessMs)}</span>
                  {/if}
                  {#if d.isOtCut}
                    <span class="rebal-cut-tag">✂ OT cut</span>
                  {/if}
                  <span class="rebal-view-hint">&#9654; logs</span>
                </button>
              {/each}
            </div>
          {/if}

          <!-- Recipients -->
          {#if rebalSummary.recipients.length}
            <div class="rebal-section">
              <p class="rebal-section-lbl rebal-lbl-recipient">&#128229; Receiving hours</p>
              {#each rebalSummary.recipients as r}
                <button class="rebal-row {r.isExcessOt ? 'rebal-row--excess-ot' : 'rebal-row--recipient'}"
                  on:click={() => selectedDate.set(r.key)}
                  title="View logs for {fmtKeyShort(r.key)}"
                >
                  <span class="rebal-day">{fmtKeyShort(r.key)}</span>
                  <div class="rebal-flow">
                    <span class="rebal-orig">{fmtDuration(r.originalMs)}</span>
                    <span class="rebal-arr">&rarr;</span>
                    <span class="rebal-new {r.isExcessOt ? 'rebal-new--excess-ot' : 'rebal-new--recipient'}">{fmtDuration(r.newMs)}</span>
                  </div>
                  <span class="rebal-badge {r.isExcessOt ? 'rebal-badge--excess-ot' : 'rebal-badge--recipient'}">{fmtDuration(r.deltaMs, true)}</span>
                  {#if r.isExcessOt}
                    <span class="rebal-excess-ot-tag">+OT</span>
                  {/if}
                  <span class="rebal-view-hint">&#9654; logs</span>
                </button>
              {/each}
            </div>
          {/if}

          <!-- Footer status -->
          {#if rebalancing.noViolations}
            <div class="rebal-footer rebal-footer--ok">
              <span>&#10003;</span>
              <span>All days would land between {$minimumDailyHours}h and {$maximumDailyHours}h after these adjustments.</span>
            </div>
          {:else}
            <div class="rebal-footer rebal-footer--warn">
              <span>&#9888;</span>
              <div>
                <p>Not enough surplus to cover all violations.</p>
                {#if rebalancing.stillUnderMin.length}
                  <p class="rebal-footer-detail">Still under {$minimumDailyHours}h: {rebalancing.stillUnderMin.map(fmtKeyShort).join(' &middot; ')}</p>
                {/if}
                {#if rebalancing.stillAboveMax.length}
                  <p class="rebal-footer-detail">Still above {$maximumDailyHours}h: {rebalancing.stillAboveMax.map(fmtKeyShort).join(' &middot; ')}</p>
                {/if}
              </div>
            </div>
          {/if}

        {/if}

        <!-- Rebalance history -->
        {#if historyLoading}
          <p class="rebal-history-loading">Loading history…</p>
        {:else if monthHistory.length > 0}
          <div class="rebal-history">
            <p class="rebal-section-lbl" style="margin-bottom: 0.5rem;">↩ Applied this month ({monthHistory.length})</p>

            <!-- Original state row -->
            <div class="rebal-history-row">
              <div class="rebal-history-meta">
                <span class="rebal-history-label">Original (before any rebalance)</span>
              </div>
              <button class="btn btn-sm {viewingEntryIdx === 0 ? 'btn-primary' : 'btn-secondary'}"
                on:click={() => viewingEntryIdx = viewingEntryIdx === 0 ? null : 0}>
                {viewingEntryIdx === 0 ? '👁 Viewing' : 'View'}
              </button>
            </div>

            {#each monthHistory as entry, i}
              <div class="rebal-history-row {i === monthHistory.length - 1 ? 'rebal-history-row--latest' : ''}">
                <div class="rebal-history-meta">
                  <span class="rebal-history-label">Rebalance {i + 1}</span>
                  <span class="rebal-history-ts">{new Date(entry.applied_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                  <span class="rebal-history-summary">
                    {[entry.summary.updates && `${entry.summary.updates}e`, entry.summary.inserts && `${entry.summary.inserts}a`, entry.summary.deletes && `${entry.summary.deletes}d`].filter(Boolean).join(' ')}
                    · OT {fmtDuration(entry.summary.otBefore, true)} → {fmtDuration(entry.summary.otAfter, true)}
                  </span>
                </div>
                <div class="rebal-history-actions">
                  <button class="btn btn-sm {viewingEntryIdx === i + 1 ? 'btn-primary' : 'btn-secondary'}"
                    on:click={() => viewingEntryIdx = viewingEntryIdx === i + 1 ? null : i + 1}>
                    {viewingEntryIdx === i + 1 ? '👁 Viewing' : 'View'}
                  </button>
                  {#if i === monthHistory.length - 1 && viewingEntryIdx === null}
                    <button class="btn btn-sm btn-danger" on:click={revertLatestRebalance} disabled={isSaving}>
                      ↩ Revert
                    </button>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}

      </div>
    {/if}
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
        <span class="pill pill-muted">{viewDayLogs.length} logs</span>
        <select bind:value={$logResolution} class="res-select">
          <option value="compact">Compact</option>
          <option value="full">Full</option>
        </select>
        {#if viewingEntryIdx === null}
          <button class="btn btn-sm btn-primary" on:click={startNewLog}>+ Add Log</button>
        {:else}
          <span class="pill pill-muted">Read-only</span>
        {/if}
      </div>
    </div>

    <div class="day-type-row">
      {#if selDayIsOff}
        <span class="day-type-badge day-type-badge--off">🏖 Off Day{$dayOverrides[$selectedDate] != null ? ' (override)' : ''}</span>
        <button class="btn btn-sm btn-secondary" on:click={() => setDayOverride($selectedDate, 'work')}>Mark as Work Day</button>
      {:else}
        <span class="day-type-badge day-type-badge--work">💼 Work Day{$dayOverrides[$selectedDate] != null ? ' (override)' : ''}</span>
        <button class="btn btn-sm btn-secondary" on:click={() => setDayOverride($selectedDate, 'off')}>Mark as Off Day</button>
      {/if}
      {#if $dayOverrides[$selectedDate] != null}
        <button class="btn btn-sm btn-secondary" on:click={() => removeDayOverride($selectedDate)}>× Revert to default</button>
      {/if}
    </div>

    {#if showRebalancing}
      {@const isStillAboveMax = rebalancing?.stillAboveMax?.includes($selectedDate) ?? false}
      {@const hasRebalDelta   = rebalMap[$selectedDate] != null}
      {@const selDelta        = rebalMap[$selectedDate] ?? 0}
      {@const selNewNet       = selNetMs + selDelta}
      {@const maxMs           = $maximumDailyHours * 3_600_000}
      {@const excessMs        = Math.max(0, selNewNet - maxMs)}
      {#if hasRebalDelta || isStillAboveMax}
        {@const isDonor = selDelta < 0 || isStillAboveMax}
        {@const isExcessOtRec = !isDonor && (rebalancing?.excessOtRecipients?.has($selectedDate) ?? false)}
        {@const finalTarget = isStillAboveMax ? maxMs : selNewNet}
        {@const selOt = selDayIsOff ? selNetMs : selNetMs - ($requiredHours * 3_600_000)}
        {@const newOt = selDayIsOff ? finalTarget : finalTarget - ($requiredHours * 3_600_000)}
        <div class="rebal-day-banner {isDonor ? 'rebal-day-banner--donor' : isExcessOtRec ? 'rebal-day-banner--excess-ot' : 'rebal-day-banner--recipient'}">
          <div class="rebal-day-banner-icon">{isDonor ? '📤' : isExcessOtRec ? '📊' : '📥'}</div>
          <div class="rebal-day-banner-body">
            <p class="rebal-day-banner-title">
              {#if isStillAboveMax && excessMs > 0}
                This day is giving hours away — {fmtDuration(excessMs)} excess must be trimmed
              {:else if isDonor}
                This day is giving hours away
              {:else if isExcessOtRec}
                This day is receiving redistributed overtime
              {:else}
                This day needs more hours
              {/if}
            </p>

            <!-- Flow row: show redistribution step + trim step if still-above-max -->
            {#if isStillAboveMax && hasRebalDelta && excessMs > 0}
              <div class="rebal-day-banner-row">
                <span class="rebal-day-banner-label">Now:</span>
                <strong class="rebal-day-banner-val">{fmtDuration(selNetMs)}</strong>
                <span class="rebal-day-banner-arrow">→</span>
                <span class="rebal-day-banner-label">Redistribute:</span>
                <strong class="rebal-day-banner-val">{fmtDuration(selNewNet)}</strong>
                <span class="rebal-day-banner-badge donor">{fmtDuration(selDelta, true)}</span>
                <span class="rebal-day-banner-arrow">→</span>
                <span class="rebal-day-banner-label">Trim to max:</span>
                <strong class="rebal-day-banner-val rebal-day-banner-target">{fmtDuration(maxMs)}</strong>
                <span class="rebal-day-banner-badge rebal-excess-inline">-{fmtDuration(excessMs)}</span>
              </div>
            {:else}
              <div class="rebal-day-banner-row">
                <span class="rebal-day-banner-label">Now:</span>
                <strong class="rebal-day-banner-val">{fmtDuration(selNetMs)}</strong>
                <span class="rebal-day-banner-arrow">→</span>
                <span class="rebal-day-banner-label">Target:</span>
                <strong class="rebal-day-banner-val rebal-day-banner-target">{fmtDuration(finalTarget)}</strong>
                <span class="rebal-day-banner-badge {isDonor ? 'donor' : 'recipient'}">{fmtDuration(finalTarget - selNetMs, true)}</span>
              </div>
            {/if}

            <!-- OT before/after -->
            <div class="rebal-day-banner-row" style="margin-top: 0.25rem;">
              <span class="rebal-day-banner-label">OT Before:</span>
              <strong class="rebal-day-banner-val" style="color: {selOt < 0 ? 'var(--color-ot-neg)' : 'var(--color-ot-pos)'}">{selOt < 0 ? '-' : '+'}{fmtDuration(Math.abs(selOt))}</strong>
              <span class="rebal-day-banner-arrow">→</span>
              <span class="rebal-day-banner-label">OT After:</span>
              <strong class="rebal-day-banner-val rebal-day-banner-target" style="color: {newOt < 0 ? 'var(--color-ot-neg)' : 'var(--color-ot-pos)'}">{newOt < 0 ? '-' : '+'}{fmtDuration(Math.abs(newOt))}</strong>
            </div>

            <!-- Excess warning -->
            {#if isStillAboveMax && excessMs > 0}
              <div class="rebal-excess-warning">
                ✂ {fmtDuration(excessMs)} cannot be redistributed — trim the highlighted home log below to reach {fmtDuration(maxMs)}.
              </div>
            {/if}

            <p class="rebal-day-banner-hint">
              {#if isExcessOtRec}
                These extra OT hours come from an above-max day. Add them to your home log to complete the redistribution.
              {:else}
                Adjust the highlighted log entry below to hit {fmtDuration(finalTarget)}.
              {/if}
            </p>
          </div>
        </div>
      {/if}
    {/if}

    {#if showRebalancing && logAdjustmentSuggestion}
      {#if logAdjustmentSuggestion.type === 'create_blocks' && logAdjustmentSuggestion.blocks.some(b => b.kind === 'new_block')}
        {@const newBlocks = logAdjustmentSuggestion.blocks.filter(b => b.kind === 'new_block')}
        <div class="suggestion-card">
          <div class="suggestion-card-header">
            <span class="suggestion-card-icon">✨</span>
            <span class="suggestion-card-title">Suggested home session{newBlocks.length > 1 ? 's' : ''}</span>
            {#if logAdjustmentSuggestion.isPartial}
              <span class="badge badge-warning" style="margin-left: auto;">Partial — some hours couldn't fit</span>
            {/if}
          </div>
          {#each newBlocks as block, i}
            <div class="suggestion-session-row">
              <div class="suggestion-session-info">
                {#if newBlocks.length > 1}<span class="suggestion-session-label">{i === 0 ? 'Evening' : 'Morning'}</span>{/if}
                <span class="pill pill-home">home</span>
                <strong class="tabnum">{fmtTs(block.resumeTs)}</strong>
                <span class="suggestion-session-arrow">→</span>
                <strong class="tabnum">{fmtTs(block.pauseTs)}</strong>
                <span class="suggestion-delta">+{fmtDuration(block.durationMs)}</span>
              </div>
              <button class="btn btn-sm btn-primary" on:click={() => applyBlock(block)} disabled={isSaving}>✨ Apply</button>
            </div>
          {/each}
          {#if newBlocks.length > 1}
            <div class="suggestion-card-footer">
              <span class="suggestion-total">Total: +{fmtDuration(logAdjustmentSuggestion.totalDeltaMs)}</span>
            </div>
          {/if}
        </div>
      {:else if logAdjustmentSuggestion.type === 'create_block_logs'}
        {@const durMs = new Date(logAdjustmentSuggestion.pauseTs).getTime() - new Date(logAdjustmentSuggestion.resumeTs).getTime()}
        <div class="suggestion-card">
          <div class="suggestion-card-header">
            <span class="suggestion-card-icon">✨</span>
            <span class="suggestion-card-title">Suggested home session</span>
            {#if logAdjustmentSuggestion.isPartial}
              <span class="badge badge-warning" style="margin-left: auto;">Partial</span>
            {/if}
          </div>
          <div class="suggestion-session-row">
            <div class="suggestion-session-info">
              <span class="pill pill-home">home</span>
              <strong class="tabnum">{fmtTs(logAdjustmentSuggestion.resumeTs)}</strong>
              <span class="suggestion-session-arrow">→</span>
              <strong class="tabnum">{fmtTs(logAdjustmentSuggestion.pauseTs)}</strong>
              <span class="suggestion-delta">+{fmtDuration(durMs)}</span>
            </div>
            <button class="btn btn-sm btn-primary" on:click={() => applyBlock(logAdjustmentSuggestion)} disabled={isSaving}>
              ✨ {logAdjustmentSuggestion.isPartial ? 'Apply (Partial)' : 'Apply'}
            </button>
          </div>
        </div>
      {/if}
    {/if}

    {#if !selDayIsOff && selNetMs > 0 && selNetMs < $minimumDailyHours * 3_600_000}
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
            {#each tableRows as row (row.kind === 'log' ? row.log.id : row.ts + '_' + row.kind)}
              {#if row.kind === 'log'}
                {@const log = row.log}
                <tr
                  class:editing={$editingLogId === log.id}
                  class:suggested-row={row.isSugg || !!row.extendSugg}
                  class:delete-suggested-row={row.isDeleteSugg}
                >
                  <td class="tabnum" style="min-width: 85px;">
                    {#if row.isSugg}
                      <div style="display: flex; flex-direction: column; gap: 2px;">
                        <span style="text-decoration: line-through; opacity: 0.5;">{fmtTs(log.timestamp)}</span>
                        <strong class="cal-delta {logAdjustmentSuggestion.deltaMs > 0 ? 'pos' : 'neg'}">{fmtTs(logAdjustmentSuggestion.newTs)}</strong>
                      </div>
                    {:else if row.extendSugg}
                      <div style="display: flex; flex-direction: column; gap: 2px;">
                        <span style="text-decoration: line-through; opacity: 0.5;">{fmtTs(log.timestamp)}</span>
                        <strong class="cal-delta pos">{fmtTs(row.extendSugg.newTs)}</strong>
                      </div>
                    {:else}
                      {fmtTs(log.timestamp)}
                    {/if}
                  </td>
                  <td><span class="pill pill-{log.platform === 'office' ? 'office' : 'home'}">{log.platform}</span></td>
                  <td><span class="pill {log.action === 'resume' ? 'pill-live' : 'pill-muted'}">{log.action}</span></td>
                  {#if $logResolution === 'full'}<td class="tabnum muted">{fmtDate(log.timestamp)}</td>{/if}
                  <td class="note-cell">{log.note || '—'}</td>
                  {#if $logResolution === 'full'}<td class="muted tabnum">{fmtTs(log.created_at)}</td>{/if}
                  <td style="display: flex; gap: 4px; flex-wrap: wrap;">
                    {#if row.isSugg}
                      <button class="btn btn-sm btn-primary" style="padding: 2px 8px; font-size: 0.75rem; white-space: nowrap; box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 30%, transparent);" on:click={applySuggestion} disabled={isSaving}>
                        {logAdjustmentSuggestion.isPartial ? '✨ Apply (Partial)' : '✨ Apply'}
                      </button>
                    {:else if row.extendSugg}
                      <button class="btn btn-sm btn-primary" style="padding: 2px 8px; font-size: 0.75rem; white-space: nowrap;" on:click={() => applyExtendResume(log.id, row.extendSugg.newTs)} disabled={isSaving}>
                        ✨ Extend (+{fmtDuration(row.extendSugg.durationMs)})
                      </button>
                    {:else if row.isDeleteSugg && log.action === 'resume'}
                      <button class="btn btn-sm btn-danger" style="padding: 2px 8px; font-size: 0.75rem; white-space: nowrap;" on:click={() => deleteSession(logAdjustmentSuggestion.resumeLogId, logAdjustmentSuggestion.pauseLogId)} disabled={isSaving}>
                        🗑 Delete session{logAdjustmentSuggestion.isPartial ? ' (Partial)' : ''}
                      </button>
                    {/if}
                    <button class="btn btn-sm btn-secondary" on:click={() => startEdit(log)}>✏️ Edit</button>
                  </td>
                </tr>
              {:else if row.kind === 'new_log'}
                <tr class="suggested-row">
                  <td class="tabnum" style="min-width: 85px;"><strong class="cal-delta pos">{fmtTs(logAdjustmentSuggestion.newTs)}</strong></td>
                  <td><span class="pill pill-home">home</span></td>
                  <td><span class="pill pill-{logAdjustmentSuggestion.action}">{logAdjustmentSuggestion.action}</span></td>
                  <td class="note-cell"><span class="badge badge-success">Suggestion</span></td>
                  <td style="display: flex; gap: 4px;">
                    <button class="btn btn-sm btn-primary" on:click={() => applyCreateLog(logAdjustmentSuggestion.action, logAdjustmentSuggestion.newTs)}>
                      ✨ {logAdjustmentSuggestion.isPartial ? 'Apply (Partial)' : 'Apply'}
                    </button>
                  </td>
                </tr>
              {/if}
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
    grid-template-columns: 380px 1fr;
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
    .cal-filters { gap: 2px; }
    .filter-btn { font-size: 0.62rem; padding: 4px 2px; }
  }

  /* Calendar */
  .cal-panel { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 1rem; box-shadow: var(--shadow-sm); position: sticky; top: 72px; overflow-x: hidden; overflow-y: auto; max-height: calc(100dvh - 80px); }
  .cal-nav { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
  .cal-title { flex: 1; text-align: center; font-size: 0.95rem; }
  .cal-nav-right { display: flex; gap: 0.25rem; }
  .cal-meta { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.5rem; }
  .cal-stats { display: flex; gap: 0.375rem; flex-shrink: 0; }
  .cal-filters { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; margin-bottom: 0.75rem; }
  .filter-btn {
    font-size: 0.7rem; font-weight: 600; font-family: var(--font);
    padding: 5px 4px; border-radius: var(--radius-sm); text-align: center;
    border: 1.5px solid var(--color-border); color: var(--color-text-muted);
    background: var(--color-surface-2); cursor: pointer; white-space: nowrap;
    transition: background var(--transition), color var(--transition), border-color var(--transition);
  }
  .filter-btn:hover { border-color: var(--color-primary); color: var(--color-text); }
  .filter-btn--neg      { background: var(--color-ot-neg-subtle);  color: var(--color-ot-neg);  border-color: var(--color-ot-neg); }
  .filter-btn--pos      { background: color-mix(in srgb, hsl(38 95% 55%) 15%, transparent); color: hsl(38 75% 40%); border-color: hsl(38 85% 55%); }
  .filter-btn--live     { background: var(--color-live-subtle);    color: var(--color-live);    border-color: var(--color-live); }
  .filter-btn--warn     { background: color-mix(in srgb, hsl(38 90% 50%) 15%, transparent); color: hsl(38 80% 40%); border-color: hsl(38 80% 50%); }
  .filter-btn--rebalance { background: var(--color-primary-subtle); color: var(--color-primary); border-color: var(--color-primary); }
  [data-theme="dark"] .filter-btn--pos  { color: hsl(38 90% 65%); }
  [data-theme="dark"] .filter-btn--warn { color: hsl(38 90% 65%); }
  .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
  .cal-day-name { text-align: center; font-size: 0.7rem; font-weight: 700; color: var(--color-text-muted); padding: 4px 0; text-transform: uppercase; }
  .cal-cell--empty { background: transparent; }
  .cal-cell {
    background: var(--color-surface-2); border: 1.5px solid transparent;
    border-radius: var(--radius-sm); padding: 5px 4px;
    display: flex; flex-direction: column; align-items: center; gap: 2px;
    cursor: pointer; min-height: 72px; min-width: 0; overflow: hidden;
    transition: border-color var(--transition), background var(--transition);
  }
  .cal-cell:hover { border-color: var(--color-primary); background: var(--color-primary-subtle); }
  .cal-cell--today .cal-day-num { background: var(--color-primary); color: #fff; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; }
  .cal-cell--selected { border-color: var(--color-primary) !important; box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 30%, transparent); }
  .cal-cell--ot-pos { border-left: 3px solid var(--color-ot-pos); }
  .cal-cell--ot-neg { border-left: 3px solid var(--color-ot-neg); }
  .cal-cell--under-min { box-shadow: inset 0 0 0 1.5px var(--color-ot-neg); }
  .cal-cell--above-max { box-shadow: inset 0 0 0 1.5px hsl(38 95% 55%); }
  .cal-cell--filtered-out { opacity: 0.15; pointer-events: none; }
  .cal-cell--off-day { background: color-mix(in srgb, var(--color-text-muted) 6%, var(--color-surface-2)); }
  .cal-cell--off-day .cal-day-num { color: var(--color-text-muted); }
  .cal-cell--override { outline: 1.5px dashed var(--color-primary); outline-offset: -2px; }
  .cal-cell--open-session   { border-bottom: 3px solid var(--color-live); }
  .cal-cell--unopen-session { border-bottom: 3px solid hsl(38 90% 50%); }
  .cal-day-num { font-size: 0.9rem; font-weight: 600; }
  .cal-net { font-size: 0.72rem; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
  .cal-ot { font-size: 0.7rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .cal-ot.pos { color: var(--color-ot-pos); }
  .cal-ot.neg { color: var(--color-ot-neg); }

  /* Rebalancing cell overlays */
  .cal-cell--rebal-donor     { border-right: 3px solid hsl(38 95% 55%); }
  .cal-cell--rebal-recipient { border-right: 3px solid var(--color-ot-pos); }
  .cal-net--orig { font-size: 0.6rem; text-decoration: line-through; opacity: 0.45; }
  .cal-net--new  { font-size: 0.72rem; font-weight: 700; color: var(--color-primary); }
  .cal-delta     { font-size: 0.65rem; font-weight: 700; }
  .cal-delta.pos { color: var(--color-ot-pos); }
  .cal-delta.neg { color: hsl(38 95% 55%); }

  /* ── Rebalancing panel ────────────────────────────────────── */
  .rebal-panel {
    margin-top: 0.875rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    overflow: hidden;
    font-size: 0.8rem;
  }

  /* Header */
  .rebal-hd {
    display: flex; align-items: center; gap: 0.6rem;
    padding: 0.65rem 0.875rem;
    background: color-mix(in srgb, var(--color-primary) 8%, var(--color-surface));
    border-bottom: 1px solid var(--color-border);
  }
  .rebal-hd-icon { font-size: 1.15rem; line-height: 1; }
  .rebal-hd-title { font-weight: 700; font-size: 0.82rem; color: var(--color-text); }
  .rebal-hd-sub   { font-size: 0.72rem; color: var(--color-text-muted); margin-top: 1px; }
  .rebal-hd-hint  { font-size: 0.68rem; color: var(--color-primary); margin-top: 3px; opacity: 0.8; }
  /* OT cut box */
  .ot-cut-box {
    margin-top: 0.5rem; width: 100%;
    background: var(--color-surface-2); border: 1px solid var(--color-border);
    border-radius: 6px; padding: 0.6rem 0.875rem;
    display: flex; flex-direction: column; gap: 0.45rem;
  }
  .ot-cut-toggle {
    display: flex; align-items: center; gap: 0.45rem;
    font-size: 0.82rem; font-weight: 600; color: var(--color-text);
    cursor: pointer;
  }
  .ot-cut-toggle input { cursor: pointer; }
  .ot-cut-controls { display: flex; align-items: center; gap: 0.7rem; }
  .ot-cut-slider { flex: 1; accent-color: var(--color-primary); }
  .ot-cut-readout { font-size: 0.8rem; font-weight: 700; white-space: nowrap; color: var(--color-text); }
  .ot-cut-hint { font-size: 0.72rem; color: var(--color-text-muted); line-height: 1.4; margin: 0; }
  .rebal-cut-tag {
    font-size: 0.66rem; font-weight: 700; color: hsl(38 95% 40%);
    background: color-mix(in srgb, hsl(38 95% 55%) 15%, transparent);
    border-radius: 4px; padding: 0.1rem 0.35rem; white-space: nowrap;
  }
  /* OT projection box */
  .ot-projection-box {
    margin-top: 0.5rem; width: 100%;
    background: var(--color-surface-2); border: 1px solid var(--color-border);
    border-radius: 6px; padding: 0.65rem 0.875rem;
    display: flex; flex-direction: column; gap: 0.5rem;
  }
  .ot-proj-row { display: flex; align-items: center; gap: 0.875rem; flex-wrap: wrap; }
  .ot-proj-col { display: flex; flex-direction: column; }
  .ot-proj-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted); }
  .ot-proj-val { font-size: 1.05rem; }
  .ot-proj-arrow { color: var(--color-text-muted); font-size: 1rem; }
  .ot-proj-delta {
    font-size: 0.88rem; font-weight: 700;
    background: var(--color-surface); border: 1px solid var(--color-border);
    border-radius: 4px; padding: 0.1rem 0.4rem;
  }
  .ot-proj-breakdown summary {
    font-size: 0.78rem; color: var(--color-text-muted);
    cursor: pointer; user-select: none; list-style: none;
  }
  .ot-proj-breakdown summary::marker, .ot-proj-breakdown summary::-webkit-details-marker { display: none; }
  .ot-proj-table {
    width: 100%; font-size: 0.78rem;
    border-collapse: collapse; margin-top: 0.35rem;
  }
  .ot-proj-table th, .ot-proj-table td {
    padding: 0.2rem 0.35rem; text-align: left;
    border-bottom: 1px solid var(--color-border);
  }
  .ot-proj-table th {
    color: var(--color-text-muted); font-weight: 600;
    text-transform: uppercase; font-size: 0.68rem; letter-spacing: 0.03em;
  }
  .ot-proj-steps { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.5rem; margin-bottom: 0.6rem; }
  .ot-proj-step {
    display: flex; align-items: flex-start; gap: 0.5rem;
    font-size: 0.75rem; color: var(--color-text-muted); line-height: 1.45;
    background: var(--color-surface); border: 1px solid var(--color-border);
    border-radius: 5px; padding: 0.35rem 0.5rem;
  }
  .ot-proj-step--warn {
    background: color-mix(in srgb, hsl(38 95% 55%) 10%, transparent);
    border-color: color-mix(in srgb, hsl(38 95% 55%) 35%, transparent);
    color: hsl(38 65% 32%);
  }
  [data-theme="dark"] .ot-proj-step--warn { color: hsl(38 85% 65%); }
  .ot-proj-step-num {
    flex-shrink: 0; width: 1.1rem; height: 1.1rem;
    background: var(--color-primary); color: #fff;
    border-radius: 50%; font-size: 0.65rem; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    margin-top: 1px;
  }
  .ot-proj-step--warn .ot-proj-step-num { background: hsl(38 85% 48%); }
  .ot-proj-unplaced {
    font-size: 0.75rem; margin: 0.4rem 0 0;
    padding: 0.3rem 0.5rem; border-radius: 4px;
    background: color-mix(in srgb, hsl(38 95% 55%) 12%, transparent);
    color: hsl(38 70% 35%); border: 1px solid color-mix(in srgb, hsl(38 95% 55%) 30%, transparent);
  }
  [data-theme="dark"] .ot-proj-unplaced { color: hsl(38 90% 65%); }

  .rebal-violations { display: flex; flex-direction: column; gap: 0.2rem; width: 100%; }
  .rebal-violation-item { font-size: 0.72rem; font-weight: 600; padding: 3px 8px; border-radius: 4px; }
  .rebal-violation--max { background: color-mix(in srgb, hsl(38 95% 55%) 15%, transparent); color: hsl(38 80% 38%); }
  [data-theme="dark"] .rebal-violation--max { color: hsl(38 95% 65%); }
  .rebal-violation--min { background: color-mix(in srgb, var(--color-ot-neg) 12%, transparent); color: var(--color-ot-neg); }

  /* Clean / no-violation state */
  .rebal-clean {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.75rem 0.875rem;
    color: var(--color-ot-pos); font-size: 0.8rem;
  }
  .rebal-clean-icon { font-size: 1.1rem; }

  /* Sections */
  .rebal-section { padding: 0.5rem 0.875rem 0.25rem; }
  .rebal-section + .rebal-section { border-top: 1px solid var(--color-border); }
  .rebal-section-lbl {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.04em;
    text-transform: uppercase; margin-bottom: 0.375rem;
  }
  .rebal-lbl-donor     { color: hsl(38 95% 55%); }
  .rebal-lbl-recipient { color: var(--color-ot-pos); }

  /* Row (now a button) */
  .rebal-row {
    display: grid;
    grid-template-columns: 1fr auto auto auto;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    border-radius: var(--radius-sm);
    margin-bottom: 0.25rem;
    width: 100%;
    text-align: left;
    border: none;
    cursor: pointer;
    transition: filter 0.15s, box-shadow 0.15s;
  }
  .rebal-row:hover { filter: brightness(1.06); box-shadow: 0 0 0 1.5px var(--color-primary); }
  .rebal-row--donor     { background: color-mix(in srgb, hsl(38 95% 55%) 8%,  var(--color-surface-2)); }
  .rebal-row--recipient { background: color-mix(in srgb, var(--color-ot-pos) 8%, var(--color-surface-2)); }
  .rebal-row--excess-ot { background: color-mix(in srgb, hsl(270 70% 60%) 8%, var(--color-surface-2)); }

  .rebal-view-hint {
    font-size: 0.65rem; color: var(--color-primary); opacity: 0;
    transition: opacity 0.15s; white-space: nowrap;
  }
  .rebal-row:hover .rebal-view-hint { opacity: 1; }

  .rebal-day  { font-weight: 600; font-size: 0.78rem; white-space: nowrap; }
  .rebal-flow { display: flex; align-items: center; gap: 0.3rem; font-variant-numeric: tabular-nums; }
  .rebal-orig { color: var(--color-text-muted); text-decoration: line-through; font-size: 0.72rem; }
  .rebal-arr  { color: var(--color-text-muted); font-size: 0.7rem; }
  .rebal-new  { font-weight: 700; font-size: 0.78rem; }
  .rebal-new--donor     { color: hsl(38 95% 55%); }
  .rebal-new--recipient { color: var(--color-ot-pos); }
  .rebal-new--excess-ot { color: hsl(270 70% 60%); font-weight: 700; }
  .rebal-new--excess    { color: var(--color-ot-neg); font-weight: 700; }
  .rebal-excess-tag {
    font-size: 0.65rem; font-weight: 700;
    padding: 1px 5px; border-radius: 999px; white-space: nowrap;
    background: color-mix(in srgb, var(--color-ot-neg) 15%, transparent);
    color: var(--color-ot-neg);
  }

  .rebal-badge {
    font-size: 0.7rem; font-weight: 700;
    padding: 1px 5px; border-radius: 999px;
    font-variant-numeric: tabular-nums; white-space: nowrap;
  }
  .rebal-badge--donor     { background: color-mix(in srgb, hsl(38 95% 55%) 18%, transparent); color: hsl(38 95% 45%); }
  .rebal-badge--recipient { background: color-mix(in srgb, var(--color-ot-pos) 18%, transparent); color: var(--color-ot-pos); }
  .rebal-badge--excess-ot { background: color-mix(in srgb, hsl(270 70% 60%) 18%, transparent); color: hsl(270 70% 45%); }
  [data-theme="dark"] .rebal-badge--excess-ot { color: hsl(270 70% 75%); }
  .rebal-excess-ot-tag {
    font-size: 0.62rem; font-weight: 700;
    padding: 1px 5px; border-radius: 999px; white-space: nowrap;
    background: color-mix(in srgb, hsl(270 70% 60%) 18%, transparent);
    color: hsl(270 70% 45%);
  }
  [data-theme="dark"] .rebal-excess-ot-tag { color: hsl(270 70% 75%); }

  /* Footer */
  .rebal-footer {
    display: flex; align-items: flex-start; gap: 0.5rem;
    padding: 0.6rem 0.875rem;
    font-size: 0.78rem;
    border-top: 1px solid var(--color-border);
  }
  .rebal-footer--ok   { color: var(--color-ot-pos); background: color-mix(in srgb, var(--color-ot-pos) 6%, transparent); }
  .rebal-footer--warn { color: var(--color-ot-neg); background: color-mix(in srgb, var(--color-ot-neg) 6%, transparent); }
  .rebal-footer-detail { font-size: 0.72rem; margin-top: 2px; opacity: 0.85; }

  /* View mode banner */
  .view-mode-banner {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.4rem 0.75rem;
    background: var(--color-primary-subtle);
    border: 1.5px solid var(--color-primary);
    border-radius: var(--radius-sm);
    font-size: 0.8rem; font-weight: 600; color: var(--color-primary);
    margin-bottom: 0.5rem;
  }

  /* Rebalance history section */
  .rebal-history { border-top: 1px solid var(--color-border); padding: 0.75rem 0.875rem 0.5rem; }
  .rebal-history-loading { font-size: 0.78rem; color: var(--color-text-muted); padding: 0.5rem 0.875rem; }
  .rebal-history-row {
    display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
    padding: 0.35rem 0;
    border-bottom: 1px solid var(--color-border);
    font-size: 0.78rem;
  }
  .rebal-history-row:last-child { border-bottom: none; }
  .rebal-history-row--latest { background: color-mix(in srgb, var(--color-primary) 4%, transparent); border-radius: var(--radius-sm); padding: 0.35rem 0.4rem; }
  .rebal-history-meta { display: flex; flex-direction: column; gap: 1px; flex: 1; min-width: 0; }
  .rebal-history-label { font-weight: 600; color: var(--color-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rebal-history-ts { font-size: 0.72rem; color: var(--color-text-muted); }
  .rebal-history-summary { font-size: 0.72rem; color: var(--color-text-muted); }
  .rebal-history-actions { display: flex; gap: 0.25rem; flex-shrink: 0; }

  /* Day type row */
  .day-type-row {
    display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
    padding: 0.375rem 0.625rem;
    border-radius: var(--radius-sm);
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    font-size: 0.8rem;
  }
  .day-type-badge {
    font-size: 0.78rem; font-weight: 600;
    padding: 2px 8px; border-radius: 999px;
  }
  .day-type-badge--off  { background: color-mix(in srgb, var(--color-text-muted) 14%, transparent); color: var(--color-text-muted); }
  .day-type-badge--work { background: color-mix(in srgb, var(--color-primary) 12%, transparent); color: var(--color-primary); }

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

  /* Rebalancing day banner */
  .rebal-day-banner {
    display: flex; align-items: flex-start; gap: 0.75rem;
    padding: 0.875rem 1rem; border-radius: var(--radius-sm);
    border: 1px solid transparent;
  }
  .rebal-day-banner--donor {
    background: color-mix(in srgb, hsl(38 95% 55%) 10%, var(--color-surface-2));
    border-color: color-mix(in srgb, hsl(38 95% 55%) 35%, transparent);
    color: hsl(38 85% 38%);
  }
  [data-theme="dark"] .rebal-day-banner--donor { color: hsl(38 95% 65%); }
  .rebal-day-banner--recipient {
    background: color-mix(in srgb, var(--color-ot-pos) 10%, var(--color-surface-2));
    border-color: color-mix(in srgb, var(--color-ot-pos) 35%, transparent);
    color: var(--color-ot-pos);
  }
  .rebal-day-banner--excess-ot {
    background: color-mix(in srgb, hsl(270 70% 60%) 10%, var(--color-surface-2));
    border-color: color-mix(in srgb, hsl(270 70% 60%) 35%, transparent);
    color: hsl(270 70% 45%);
  }
  [data-theme="dark"] .rebal-day-banner--excess-ot { color: hsl(270 70% 75%); }
  .rebal-day-banner-icon { font-size: 1.4rem; line-height: 1; flex-shrink: 0; margin-top: 1px; }
  .rebal-day-banner-body { display: flex; flex-direction: column; gap: 0.3rem; flex: 1; }
  .rebal-day-banner-title { font-weight: 700; font-size: 0.85rem; }
  .rebal-day-banner-row {
    display: flex; align-items: center; gap: 0.4rem;
    font-variant-numeric: tabular-nums; flex-wrap: wrap;
  }
  .rebal-day-banner-label { font-size: 0.75rem; opacity: 0.75; }
  .rebal-day-banner-val   { font-size: 0.88rem; }
  .rebal-day-banner-arrow { opacity: 0.5; }
  .rebal-day-banner-target { font-size: 1rem; }
  .rebal-day-banner-badge {
    font-size: 0.72rem; font-weight: 700;
    padding: 1px 7px; border-radius: 999px; margin-left: 0.25rem;
  }
  .rebal-day-banner-badge.donor     { background: color-mix(in srgb, hsl(38 95% 55%) 20%, transparent); }
  .rebal-day-banner-badge.recipient { background: color-mix(in srgb, var(--color-ot-pos) 20%, transparent); }
  .rebal-day-banner-hint { font-size: 0.78rem; opacity: 0.8; line-height: 1.4; }
  .rebal-excess-warning {
    font-size: 0.78rem; font-weight: 600;
    padding: 4px 8px; border-radius: 4px; margin-top: 0.25rem;
    background: color-mix(in srgb, var(--color-ot-neg) 12%, transparent);
    color: var(--color-ot-neg);
  }
  .rebal-excess-inline {
    font-size: 0.7rem; font-weight: 700;
    padding: 1px 5px; border-radius: 999px;
    background: color-mix(in srgb, var(--color-ot-neg) 15%, transparent);
    color: var(--color-ot-neg);
    white-space: nowrap;
  }

  /* Suggestion block card */
  .suggestion-card {
    border: 1.5px solid color-mix(in srgb, var(--color-primary) 35%, transparent);
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-primary) 4%, var(--color-surface));
    overflow: hidden;
  }
  .suggestion-card-header {
    display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
    padding: 0.45rem 0.875rem;
    background: color-mix(in srgb, var(--color-primary) 10%, var(--color-surface-2));
    border-bottom: 1px solid color-mix(in srgb, var(--color-primary) 20%, transparent);
  }
  .suggestion-card-icon { font-size: 0.9rem; }
  .suggestion-card-title { font-size: 0.8rem; font-weight: 700; color: var(--color-primary); flex: 1; }
  .suggestion-session-row {
    display: flex; align-items: center; justify-content: space-between; gap: 0.75rem;
    padding: 0.55rem 0.875rem;
    border-bottom: 1px solid var(--color-border);
  }
  .suggestion-session-row:last-child { border-bottom: none; }
  .suggestion-session-info {
    display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;
    font-variant-numeric: tabular-nums; flex: 1; font-size: 0.875rem;
  }
  .suggestion-session-label {
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.05em; color: var(--color-text-muted); min-width: 48px;
  }
  .suggestion-session-arrow { color: var(--color-text-muted); }
  .suggestion-delta {
    font-size: 0.78rem; font-weight: 700; color: var(--color-ot-pos);
    background: color-mix(in srgb, var(--color-ot-pos) 12%, transparent);
    padding: 1px 7px; border-radius: 999px; white-space: nowrap;
  }
  .suggestion-card-footer {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.35rem 0.875rem;
    background: color-mix(in srgb, var(--color-primary) 5%, var(--color-surface-2));
    border-top: 1px solid var(--color-border);
  }
  .suggestion-total { font-size: 0.78rem; font-weight: 700; color: var(--color-primary); }

  .empty-state { text-align: center; color: var(--color-text-muted); padding: 3rem 0; font-size: 0.9rem; }

  /* Log table */
  .log-table-wrap { overflow-x: auto; border-radius: var(--radius-md); border: 1px solid var(--color-border); }
  .log-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  .log-table thead { background: var(--color-surface-2); }
  .log-table th { padding: 0.5rem 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 700; color: var(--color-text-muted); white-space: nowrap; }
  .log-table td { padding: 0.5rem 0.75rem; border-top: 1px solid var(--color-border); }
  .log-table tr:hover td { background: var(--color-surface-2); }
  .log-table tr.editing td { background: var(--color-primary-subtle); }
  .log-table tr.suggested-row td { background: color-mix(in srgb, var(--color-primary) 8%, var(--color-surface-2)); }
  .log-table tr.delete-suggested-row td { background: color-mix(in srgb, var(--color-ot-neg) 8%, var(--color-surface-2)); }
  .note-cell { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text-muted); }
  .muted { color: var(--color-text-muted); }

  /* Badges */
  .badge {
    display: inline-flex; align-items: center;
    padding: 2px 10px; border-radius: 999px;
    font-size: 0.72rem; font-weight: 700; white-space: nowrap;
  }
  .badge-success { background: color-mix(in srgb, var(--color-ot-pos) 18%, transparent); color: var(--color-ot-pos); }
  .badge-warning { background: color-mix(in srgb, hsl(38 95% 55%) 18%, transparent); color: hsl(38 85% 38%); }
  [data-theme="dark"] .badge-warning { color: hsl(38 95% 65%); }

  /* Edit panel */
  .edit-panel { margin-top: 0.5rem; }
  h3 { font-size: 1rem; font-weight: 700; margin-bottom: 1rem; }
  .edit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  @media (max-width: 540px) { .edit-grid { grid-template-columns: 1fr; } }
  .edit-actions { display: flex; gap: 0.5rem; margin-top: 1rem; flex-wrap: wrap; }
</style>
