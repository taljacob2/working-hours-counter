<script>
  import { onDestroy } from 'svelte'
  import { user, logs, selectedDate, calCursor, logResolution, editingLogId, selectedDayLogs, showToast } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'
  import { fmtDuration, dateKey, computeNetMs, computeTotalMs, byTs,
           loggedDaysInMonth, monthBounds, monthCumulativeOtMs, isOffDay } from '../lib/timeUtils.js'
  import { requiredHours, minimumDailyHours, maximumDailyHours, commuteGapMinutes, use24HourFormat, offDays, dayOverrides } from '../stores/appStore.js'

  // Live clock for open-ended spans
  let now = new Date()
  const ticker = setInterval(() => now = new Date(), 1000)
  onDestroy(() => clearInterval(ticker))

  const todayKey = dateKey()
  let filterUnderMin = false
  let filterAboveMax = false

  // ── Calendar helpers ─────────────────────────────────────────
  const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

  $: calYear  = $calCursor.getFullYear()
  $: calMonth = $calCursor.getMonth() + 1

  $: calDays = buildCalendar(calYear, calMonth)
  $: cumOt   = monthCumulativeOtMs($logs, calYear, calMonth, $requiredHours, $offDays, $dayOverrides)
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
      const dayIsOff = isOffDay(key, $offDays, $dayOverrides)
      const hasOverride = $dayOverrides[key] != null
      const otMs   = dl.length > 0 ? (dayIsOff ? netMs : netMs - reqMs) : null
      const offMs  = computeNetMs(dl.filter(l => l.platform === 'office'), (isOpen && key === todayKey) ? now : null)
      const homeMs = computeNetMs(dl.filter(l => l.platform === 'home'),   (isOpen && key === todayKey) ? now : null)
      const underMin = !dayIsOff && netMs > 0 && netMs < minMs
      const aboveMax = !dayIsOff && netMs > $maximumDailyHours * 3_600_000
      cells.push({ d, key, count: dl.length, netMs, otMs, offMs, homeMs, underMin, aboveMax, isOff: dayIsOff, hasOverride })
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
  $: selNetMs    = computeNetMs($selectedDayLogs, $selectedDate === todayKey ? now : null)
  $: selDayIsOff = isOffDay($selectedDate, $offDays, $dayOverrides)
  $: selOtMs     = $selectedDayLogs.length > 0 ? (selDayIsOff ? selNetMs : selNetMs - $requiredHours * 3_600_000) : null

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

  function fmtKeyShort(key) {
    return new Date(key + 'T12:00:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
  }

  function suggestRebalancing(cells, minMs, maxMs, reqMs, offDays = [], dayOverrides = {}) {
    const dayIsOff = key => isOffDay(key, offDays, dayOverrides)

    // Mutable working copies — only logged days matter
    const days = cells
      .filter(c => c !== null && c.count > 0)
      .map(c => ({ key: c.key, currentMs: c.netMs, offMs: c.offMs, isOff: dayIsOff(c.key) }))

    const transfers = []

    // Pass 1: off-day home hours → working days.
    // Priority 1: fill under-required days first. Priority 2: fill under-max days.
    // Off days go first so their surplus is never crowded out by working-day OT donors.
    for (const donor of days.filter(d => d.isOff && d.currentMs > d.offMs).sort((a, b) => b.currentMs - a.currentMs)) {
      const floor = donor.offMs
      while (donor.currentMs > floor) {
        const underReq = days
          .filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < reqMs)
          .sort((a, b) => a.currentMs - b.currentMs)[0]
        const underMax = !underReq && days
          .filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < maxMs)
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
      .filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < reqMs)
      .sort((a, b) => a.currentMs - b.currentMs)

    for (const rec of recipients) {
      while (rec.currentMs < reqMs) {
        const aboveMaxDonors = days
          .filter(d => !d.tappedOut && !d.isOff && d.currentMs > maxMs)
          .sort((a, b) => b.currentMs - a.currentMs)
        const otDonors = days
          .filter(d => !d.tappedOut && !d.isOff && d.currentMs > reqMs && d.currentMs <= maxMs)
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
    // Runs after Pass 2 when above-max donors still have surplus that couldn't go to
    // under-required recipients (because they were all already at required hours).
    for (const d of days) d.tappedOut3 = false
    const pass3Recipients = days
      .filter(d => !d.isOff && d.currentMs > 0 && d.currentMs < maxMs)
      .sort((a, b) => a.currentMs - b.currentMs)

    for (const rec of pass3Recipients) {
      while (rec.currentMs < maxMs) {
        const donor = days
          .filter(d => !d.isOff && !d.tappedOut3 && d.currentMs > maxMs)
          .sort((a, b) => b.currentMs - a.currentMs)[0]
        if (!donor) break
        const floor    = Math.max(maxMs, donor.offMs)
        const available = donor.currentMs - floor
        if (available <= 0) { donor.tappedOut3 = true; continue }
        const needed   = maxMs - rec.currentMs
        const transfer = Math.min(available, needed)
        donor.currentMs -= transfer
        rec.currentMs   += transfer
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

  $: rebalancing = showRebalancing
    ? suggestRebalancing(
        calDays.filter(Boolean),
        $minimumDailyHours * 3_600_000,
        $maximumDailyHours * 3_600_000,
        $requiredHours    * 3_600_000,
        $offDays,
        $dayOverrides
      )
    : null

  // Per-cell delta map: key → net milliseconds shifted (negative = donated, positive = received)
  $: rebalMap = (() => {
    if (!rebalancing) return {}
    const map = {}
    for (const t of rebalancing.transfers) {
      map[t.from] = (map[t.from] ?? 0) - t.ms
      map[t.to]   = (map[t.to]   ?? 0) + t.ms
    }
    return map
  })()

  // Per-day summary for the redesigned panel
  $: rebalSummary = (() => {
    if (!rebalancing || !Object.keys(rebalMap).length) return { donors: [], recipients: [] }
    const donors = [], recipients = []
    for (const [key, deltaMs] of Object.entries(rebalMap)) {
      const cell = calDays.find(c => c && c.key === key)
      if (!cell) continue
      // isExcessOt = this day received Pass-3 excess-OT hours (may also have received normal hours)
      const isExcessOt = rebalancing.excessOtRecipients.has(key)
      const entry = { key, originalMs: cell.netMs, newMs: cell.netMs + deltaMs, deltaMs, isExcessOt }
      if (deltaMs < 0) donors.push(entry)
      else             recipients.push(entry)
    }
    donors.sort((a, b) => a.deltaMs - b.deltaMs)
    recipients.sort((a, b) => b.deltaMs - a.deltaMs)
    return { donors, recipients }
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

    // Morning slot: before first log (- commute gap if office, else 1 min)
    let morningEnd = new Date(dateStr + 'T09:00:00').getTime()
    if (sortedLogs.length > 0) {
      const first   = sortedLogs[0]
      const firstTs = new Date(first.timestamp).getTime()
      morningEnd = first.platform === 'office' ? firstTs - commuteMs : firstTs - 60_000
    }
    const morningCap = Math.max(0, morningEnd - dayStart)

    const blocks = []
    let remaining = neededMs

    if (eveningCap > 0 && remaining > 0) {
      const take = Math.min(eveningCap, remaining)
      blocks.push({
        resumeTs:   new Date(eveningStart).toISOString(),
        pauseTs:    new Date(eveningStart + take).toISOString(),
        durationMs: take
      })
      remaining -= take
    }

    if (morningCap > 0 && remaining > 0) {
      const take = Math.min(morningCap, remaining)
      blocks.push({
        resumeTs:   new Date(morningEnd - take).toISOString(),
        pauseTs:    new Date(morningEnd).toISOString(),
        durationMs: take
      })
      remaining -= take
    }

    return { type: 'create_blocks', blocks, totalDeltaMs: neededMs - remaining, isPartial: remaining > 0 }
  }

  // Per-day log adjustment suggestion
  $: logAdjustmentSuggestion = (() => {
    if (!showRebalancing || $selectedDayLogs.length === 0) return null

    const isStillAboveMax = rebalancing?.stillAboveMax?.includes($selectedDate) ?? false
    const maxMs = $maximumDailyHours * 3_600_000

    // For still-above-max days the target is always maxMs (covers both the
    // redistribution portion AND the undistributable excess that must be deleted).
    let deltaMs
    if (isStillAboveMax) {
      deltaMs = -(Math.max(0, selNetMs - maxMs))
      if (deltaMs === 0) return null
    } else if (rebalMap[$selectedDate] != null) {
      deltaMs = rebalMap[$selectedDate]
      if (deltaMs === 0) return null
    } else {
      return null
    }

    const logsCopy = [...$selectedDayLogs].sort(byTs)

    // Excess-OT recipient days get new blocks at human hours, not backward-extended logs
    const isExcessOtRec = !isStillAboveMax &&
      (rebalancing?.excessOtRecipients?.has($selectedDate) ?? false)
    if (isExcessOtRec && deltaMs > 0) {
      return computeHumanHoursBlocks(logsCopy, deltaMs, $selectedDate, $commuteGapMinutes)
    }

    // Check if there is an open home resume
    let openHomeResume = null
    for (const l of logsCopy) {
      if (l.platform === 'home') {
        if (l.action === 'resume') openHomeResume = l
        else if (l.action === 'pause') openHomeResume = null
      }
    }

    // 1. If we need to ADD time, and we have an open home resume, suggest a pause to close it
    if (deltaMs > 0 && openHomeResume) {
      const curTs = new Date(openHomeResume.timestamp).getTime()
      let limitTs = new Date($selectedDate + 'T23:59:59').getTime()
      
      const nextOffice = logsCopy.find(l => l.timestamp > openHomeResume.timestamp && l.platform === 'office')
      if (nextOffice) {
        limitTs = new Date(nextOffice.timestamp).getTime() - ($commuteGapMinutes * 60_000)
      }
      
      const maxInc = limitTs - curTs
      const inc = Math.min(deltaMs, maxInc)
      if (inc > 0) {
        return {
          type: 'create_log',
          action: 'pause',
          newTs: new Date(curTs + inc).toISOString(),
          deltaMs: inc,
          isPartial: inc < deltaMs
        }
      }
    }

    let targetLogId = null
    let adjustmentMs = 0
    let originalTs = null
    let isPartial = false

    const getBenefit = (oldTsIso, newTsIso) => {
      const oldDt = new Date(oldTsIso)
      const newDt = new Date(newTsIso)
      const getDist = (dt) => {
        const center = new Date(dt)
        center.setHours(13, 30, 0, 0)
        return Math.abs(dt.getTime() - center.getTime())
      }
      return getDist(oldDt) - getDist(newDt)
    }

    if (deltaMs < 0) {
      // Need to REDUCE time
      const needed = -deltaMs
      let candidates = []

      for (let i = 0; i < logsCopy.length; i++) {
        const log = logsCopy[i]
        if (log.platform === 'home') {
          if (log.action === 'pause') {
            const prev = logsCopy[i - 1]
            if (prev && prev.action === 'resume' && prev.platform === 'home') {
              const minAllowedTs = new Date(prev.timestamp).getTime()
              const curTs = new Date(log.timestamp).getTime()
              const red = curTs - minAllowedTs
              if (red > 0) {
                const appliedRed = Math.min(red, needed)
                const newTsIso = new Date(curTs - appliedRed).toISOString()
                candidates.push({
                  logId: log.id, originalTs: log.timestamp, newTs: newTsIso, 
                  deltaMs: needed, isPartial: appliedRed < needed,
                  appliedRed, benefit: getBenefit(log.timestamp, newTsIso)
                })
              }
            }
          } else if (log.action === 'resume') {
            const next = logsCopy[i + 1]
            if (next && next.action === 'pause' && next.platform === 'home') {
              const maxAllowedTs = new Date(next.timestamp).getTime()
              const curTs = new Date(log.timestamp).getTime()
              const red = maxAllowedTs - curTs
              if (red > 0) {
                const appliedRed = Math.min(red, needed)
                const newTsIso = new Date(curTs + appliedRed).toISOString()
                candidates.push({
                  logId: log.id, originalTs: log.timestamp, newTs: newTsIso, 
                  deltaMs: needed, isPartial: appliedRed < needed,
                  appliedRed, benefit: getBenefit(log.timestamp, newTsIso)
                })
              }
            }
          }
        }
      }

      if (candidates.length > 0) {
        candidates.sort((a, b) => {
          if (b.appliedRed !== a.appliedRed) return b.appliedRed - a.appliedRed
          return b.benefit - a.benefit
        })
        const best = candidates[0]
        return { logId: best.logId, originalTs: best.originalTs, newTs: best.newTs, deltaMs: best.deltaMs, isPartial: best.isPartial }
      }
    } else {
      // Need to INCREASE time
      const needed = deltaMs
      let candidates = []

      for (let i = 0; i < logsCopy.length; i++) {
        const log = logsCopy[i]
        if (log.platform === 'home') {
          if (log.action === 'pause') {
            const next = logsCopy[i + 1]
            const curTs = new Date(log.timestamp).getTime()
            let limitTs = new Date(log.timestamp.slice(0, 10) + 'T23:59:59').getTime()
            if (next) {
              limitTs = new Date(next.timestamp).getTime()
              if (next.platform === 'office') limitTs -= ($commuteGapMinutes * 60_000)
            }
            const inc = limitTs - curTs
            if (inc > 0) {
              const appliedInc = Math.min(inc, needed)
              const newTsIso = new Date(curTs + appliedInc).toISOString()
              candidates.push({
                logId: log.id, originalTs: log.timestamp, newTs: newTsIso, 
                deltaMs: needed, isPartial: appliedInc < needed,
                appliedInc, benefit: getBenefit(log.timestamp, newTsIso)
              })
            }
          } else if (log.action === 'resume') {
            const prev = logsCopy[i - 1]
            const curTs = new Date(log.timestamp).getTime()
            let limitTs = new Date(log.timestamp.slice(0, 10) + 'T06:00:00').getTime()
            if (prev) {
              limitTs = new Date(prev.timestamp).getTime()
              if (prev.platform === 'office') limitTs += ($commuteGapMinutes * 60_000)
            }
            const inc = curTs - limitTs
            if (inc > 0) {
              const appliedInc = Math.min(inc, needed)
              const newTsIso = new Date(curTs - appliedInc).toISOString()
              candidates.push({
                logId: log.id, originalTs: log.timestamp, newTs: newTsIso, 
                deltaMs: needed, isPartial: appliedInc < needed,
                appliedInc, benefit: getBenefit(log.timestamp, newTsIso)
              })
            }
          }
        }
      }

      if (candidates.length > 0) {
        candidates.sort((a, b) => {
          if (b.appliedInc !== a.appliedInc) return b.appliedInc - a.appliedInc
          return b.benefit - a.benefit
        })
        const best = candidates[0]
        return { logId: best.logId, originalTs: best.originalTs, newTs: best.newTs, deltaMs: best.deltaMs, isPartial: best.isPartial }
      }
    }

    // Ultimate fallback if no suitable pause log was found
    if (deltaMs > 0) {
      // Suggest TWO brand new logs to start fixing the deficit
      const lastLog = logsCopy[logsCopy.length - 1]
      let startTs = new Date($selectedDate + 'T17:00:00').getTime()
      if (lastLog) {
        startTs = new Date(lastLog.timestamp).getTime()
        if (lastLog.platform === 'office') {
          startTs += ($commuteGapMinutes * 60_000)
        } else {
          startTs += 60_000 // 1 minute gap from last home log
        }
      }

      const limitTs = new Date($selectedDate + 'T23:59:59').getTime()
      let endTs = startTs + deltaMs
      let isPartialLocal = false
      if (endTs > limitTs) {
        endTs = limitTs
        isPartialLocal = true
      }

      return {
        type: 'create_block_logs',
        resumeTs: new Date(startTs).toISOString(),
        pauseTs: new Date(endTs).toISOString(),
        deltaMs: endTs - startTs,
        isPartial: isPartialLocal
      }
    }

    // Ultimate fallback for REDUCE time
    const homeLogs = logsCopy.filter(l => l.platform === 'home')
    if (homeLogs.length === 0) return null 
    
    const last = homeLogs[homeLogs.length - 1]
    const fallbackAdjustmentMs = last.action === 'pause' ? deltaMs : -deltaMs
    return {
      logId: last.id,
      originalTs: last.timestamp,
      newTs: new Date(new Date(last.timestamp).getTime() + fallbackAdjustmentMs).toISOString(),
      deltaMs: fallbackAdjustmentMs, // actual adjustment being applied
      isPartial: false
    }
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
      user_id: $user.id,
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
    const base = { user_id: $user.id, platform: 'home', date_key: $selectedDate }
    const { data: rd, error: re } = await sb.from('work_logs')
      .insert({ ...base, action: 'resume', timestamp: block.resumeTs }).select().single()
    if (re) { showToast('Error: ' + re.message, 'error'); isSaving = false; return }
    const { data: pd, error: pe } = await sb.from('work_logs')
      .insert({ ...base, action: 'pause', timestamp: block.pauseTs }).select().single()
    if (pe) { showToast('Error: ' + pe.message, 'error'); isSaving = false; return }
    logs.update(ls => [...ls, rd, pd])
    showToast('Rebalance block applied', 'success')
    isSaving = false
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
            ⚠ Under Min
          </button>
          <button 
            class="pill {filterAboveMax ? 'pill-ot-pos' : 'pill-muted'}" 
            style="cursor: pointer; border: 1.5px solid transparent;" 
            class:active-filter-max={filterAboveMax}
            on:click={() => filterAboveMax = !filterAboveMax}
            title="Filter by above {$maximumDailyHours}h maximum"
          >
            ⚠ Above Max
          </button>
          <button
            class="pill {showRebalancing ? 'pill-primary' : 'pill-muted'}"
            style="cursor: pointer; border: 1.5px solid transparent;"
            on:click={() => showRebalancing = !showRebalancing}
            title="Suggest how to redistribute hours to fix violations"
          >
            ⚖ Rebalance
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
            class:cal-cell--filtered-out={(filterUnderMin && !effectiveUnderMin) || (filterAboveMax && !effectiveAboveMax)}
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

    {#if showRebalancing && rebalancing}
      <div class="rebal-panel">

        <!-- Header -->
        <div class="rebal-hd" style="flex-direction: column; align-items: flex-start; gap: 0.5rem;">
          <div style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span class="rebal-hd-icon">&#9878;</span>
              <p class="rebal-hd-title" style="margin: 0; font-size: 1.1rem; font-weight: 600;">Hour Redistribution Plan</p>
            </div>
            {#if rebalancing.noViolations}
              <span class="badge badge-success">Balanced</span>
            {:else}
              <span class="badge badge-warning">Action Required</span>
            {/if}
          </div>
          {#if !rebalancing.noViolations}
            <div class="rebal-violations">
              {#if rebalancing.stillAboveMax.length}
                <span class="rebal-violation-item rebal-violation--max">⚠ Still above {$maximumDailyHours}h: {rebalancing.stillAboveMax.map(fmtKeyShort).join(', ')}</span>
              {/if}
              {#if rebalancing.stillUnderMin.length}
                <span class="rebal-violation-item rebal-violation--min">⚠ Still under {$minimumDailyHours}h: {rebalancing.stillUnderMin.map(fmtKeyShort).join(', ')}</span>
              {/if}
            </div>
          {/if}
          <div style="display: flex; gap: 1.5rem; margin-top: 0.5rem; background: var(--color-surface-2); padding: 0.75rem; border-radius: 6px; width: 100%; border: 1px solid var(--color-border); align-items: center;">
            <div style="display: flex; flex-direction: column;">
              <span style="font-size: 0.75rem; color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Cumulative Monthly OT</span>
              <strong style="font-size: 1.1rem; color: {cumOt < 0 ? 'var(--color-ot-neg)' : 'var(--color-ot-pos)'}">{cumOt < 0 ? '-' : '+'}{fmtDuration(Math.abs(cumOt))}</strong>
            </div>
            <div style="color: var(--color-text-muted); font-size: 0.8rem; flex: 1; font-style: italic;">Rebalancing redistributes hours between days — total monthly OT stays the same.</div>
          </div>
          <p class="rebal-hd-hint" style="margin: 0; font-size: 0.85rem;">Click any day below to view &amp; edit its logs &rarr;</p>
        </div>

        {#if !rebalancing.transfers.length}
          <div class="rebal-clean">
            <span class="rebal-clean-icon">&#10003;</span>
            <p>All logged days are already within {$minimumDailyHours}h–{$maximumDailyHours}h. Nothing to adjust.</p>
          </div>
        {:else}

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
        <span class="pill pill-muted">{$selectedDayLogs.length} logs</span>
        <select bind:value={$logResolution} class="res-select">
          <option value="compact">Compact</option>
          <option value="full">Full</option>
        </select>
        <button class="btn btn-sm btn-primary" on:click={startNewLog}>+ Add Log</button>
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
            {#each $selectedDayLogs as log (log.id)}
              {@const isSugg = logAdjustmentSuggestion?.logId === log.id}
              <tr class:editing={$editingLogId === log.id} class:suggested-row={isSugg}>
                <td class="tabnum" style="min-width: 85px;">
                  {#if isSugg}
                    <div style="display: flex; flex-direction: column; gap: 2px;">
                      <span style="text-decoration: line-through; opacity: 0.5;">{fmtTs(log.timestamp)}</span>
                      <strong class="cal-delta {logAdjustmentSuggestion.deltaMs > 0 ? 'pos' : 'neg'}">{fmtTs(logAdjustmentSuggestion.newTs)}</strong>
                    </div>
                  {:else}
                    {fmtTs(log.timestamp)}
                  {/if}
                </td>
                <td>
                  <span class="pill pill-{log.platform === 'office' ? 'office' : 'home'}">{log.platform}</span>
                </td>
                <td>
                  <span class="pill {log.action === 'resume' ? 'pill-live' : 'pill-muted'}">{log.action}</span>
                </td>
                {#if $logResolution === 'full'}<td class="tabnum muted">{fmtDate(log.timestamp)}</td>{/if}
                <td class="note-cell">{log.note || '—'}</td>
                {#if $logResolution === 'full'}<td class="muted tabnum">{fmtTs(log.created_at)}</td>{/if}
                <td style="display: flex; gap: 4px;">
                  {#if isSugg}
                    <button 
                      class="btn btn-sm btn-primary" 
                      style="padding: 2px 8px; font-size: 0.75rem; white-space: nowrap; box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 30%, transparent);" 
                      on:click={applySuggestion} 
                      disabled={isSaving}
                    >
                      {logAdjustmentSuggestion.isPartial ? '✨ Apply (Partial)' : '✨ Apply'}
                    </button>
                  {/if}
                  <button class="btn btn-sm btn-secondary" on:click={() => startEdit(log)}>✏️ Edit</button>
                </td>
              </tr>
            {/each}

            {#if logAdjustmentSuggestion?.type === 'create_blocks'}
              {#each logAdjustmentSuggestion.blocks as block, i}
                <tr class="suggested-row">
                  <td colspan="5" style="padding: 4px 10px; font-size: 0.78rem; font-weight: 600; color: hsl(270 70% 45%); background: color-mix(in srgb, hsl(270 70% 60%) 8%, var(--color-surface-2));">
                    📊 Block {i + 1}: {fmtTs(block.resumeTs)} → {fmtTs(block.pauseTs)}
                    <span style="font-weight: 400; color: var(--color-text-muted); margin-left: 4px;">({fmtDuration(block.durationMs)})</span>
                    <button
                      class="btn btn-sm btn-primary"
                      style="margin-left: 0.5rem; padding: 1px 8px; font-size: 0.72rem;"
                      on:click={() => applyBlock(block)}
                      disabled={isSaving}
                    >✨ Apply Both</button>
                  </td>
                </tr>
                <tr class="suggested-row">
                  <td class="tabnum" style="min-width: 85px;"><strong class="cal-delta pos">{fmtTs(block.resumeTs)}</strong></td>
                  <td><span class="pill pill-home">home</span></td>
                  <td><span class="pill pill-live">resume</span></td>
                  <td class="note-cell"><span class="badge badge-success">Suggestion</span></td>
                  <td style="display: flex; gap: 4px;">
                    <button class="btn btn-sm btn-secondary" style="padding: 2px 8px; font-size: 0.75rem;" on:click={() => applyCreateLog('resume', block.resumeTs)} disabled={isSaving}>Apply</button>
                  </td>
                </tr>
                <tr class="suggested-row">
                  <td class="tabnum" style="min-width: 85px;"><strong class="cal-delta pos">{fmtTs(block.pauseTs)}</strong></td>
                  <td><span class="pill pill-home">home</span></td>
                  <td><span class="pill pill-muted">pause</span></td>
                  <td class="note-cell"><span class="badge badge-success">Suggestion</span></td>
                  <td style="display: flex; gap: 4px;">
                    <button class="btn btn-sm btn-secondary" style="padding: 2px 8px; font-size: 0.75rem;" on:click={() => applyCreateLog('pause', block.pauseTs)} disabled={isSaving}>Apply</button>
                  </td>
                </tr>
              {/each}
              {#if logAdjustmentSuggestion.isPartial}
                <tr>
                  <td colspan="5" class="rebal-excess-warning" style="padding: 6px 10px; font-size: 0.78rem;">
                    ⚠ Could only fit {fmtDuration(logAdjustmentSuggestion.totalDeltaMs)} in available time slots — some hours remain unplaced.
                  </td>
                </tr>
              {/if}
            {:else if logAdjustmentSuggestion?.type === 'create_block_logs'}
              <tr class="suggested-row">
                <td class="tabnum" style="min-width: 85px;">
                  <strong class="cal-delta pos">{fmtTs(logAdjustmentSuggestion.resumeTs)}</strong>
                </td>
                <td><span class="pill pill-home">home</span></td>
                <td><span class="pill pill-resume">resume</span></td>
                <td class="note-cell"><span class="badge badge-success">Suggestion</span></td>
                <td style="display: flex; gap: 4px;">
                  <button class="btn btn-sm btn-primary" on:click={() => applyCreateLog('resume', logAdjustmentSuggestion.resumeTs)}>
                    ✨ Apply
                  </button>
                </td>
              </tr>
              <tr class="suggested-row">
                <td class="tabnum" style="min-width: 85px;">
                  <strong class="cal-delta pos">{fmtTs(logAdjustmentSuggestion.pauseTs)}</strong>
                </td>
                <td><span class="pill pill-home">home</span></td>
                <td><span class="pill pill-pause">pause</span></td>
                <td class="note-cell"><span class="badge badge-success">Suggestion</span></td>
                <td style="display: flex; gap: 4px;">
                  <button class="btn btn-sm btn-primary" on:click={() => applyCreateLog('pause', logAdjustmentSuggestion.pauseTs)}>
                    ✨ {logAdjustmentSuggestion.isPartial ? 'Apply (Partial)' : 'Apply'}
                  </button>
                </td>
              </tr>
            {:else if logAdjustmentSuggestion?.type === 'create_log'}
              <tr class="suggested-row">
                <td class="tabnum" style="min-width: 85px;">
                  <strong class="cal-delta pos">{fmtTs(logAdjustmentSuggestion.newTs)}</strong>
                </td>
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
    .cal-month-pills { gap: 0.125rem; }
  }

  /* Calendar */
  .cal-panel { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 1rem; box-shadow: var(--shadow-sm); position: sticky; top: 72px; overflow-x: hidden; overflow-y: auto; max-height: calc(100dvh - 80px); }
  .cal-nav { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
  .cal-title { flex: 1; text-align: center; font-size: 0.95rem; }
  .cal-month-pills { display: flex; gap: 0.375rem; justify-content: center; margin-top: 0.25rem; flex-wrap: wrap; }
  .cal-nav-right { display: flex; gap: 0.25rem; }
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
  .active-filter     { border-color: color-mix(in srgb, var(--color-ot-neg) 30%, transparent) !important; }
  .active-filter-max { border-color: color-mix(in srgb, hsl(38 95% 55%) 40%, transparent) !important; }
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
