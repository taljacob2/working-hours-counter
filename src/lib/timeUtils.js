/** Format milliseconds as HH:MM or +HH:MM / -HH:MM for OT */
export function fmtDuration(ms, signed = false) {
  if (ms == null || isNaN(ms)) return signed ? '±00:00' : '00:00'
  const sign = ms < 0 ? '-' : (signed && ms > 0 ? '+' : '')
  const abs = Math.abs(ms)
  const h = Math.floor(abs / 3_600_000)
  const m = Math.floor((abs % 3_600_000) / 60_000)
  return `${sign}${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** Format a Date as YYYY-MM-DD local key */
export function dateKey(d = new Date()) {
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${mo}-${day}`
}

/** Parse an ISO timestamptz string to a JS Date */
export function parseTs(ts) {
  return new Date(ts)
}

/**
 * Compute net ms from a sorted array of log entries.
 * A "resume" opens a span, a "pause" closes it.
 * If the last action is "resume" and `openEnd` is provided (a Date),
 * the span extends to openEnd.
 */
export function computeNetMs(logs, openEnd = null) {
  let net = 0
  let openAt = null
  for (const log of logs) {
    const ts = parseTs(log.timestamp).getTime()
    if (log.action === 'resume') {
      openAt = ts
    } else if (log.action === 'pause' && openAt !== null) {
      net += ts - openAt
      openAt = null
    }
  }
  if (openAt !== null && openEnd) {
    net += openEnd.getTime() - openAt
  }
  return net
}

/** Compute gross total ms (sum of all resume→pause spans, no open-ended) */
export function computeTotalMs(logs) {
  return computeNetMs(logs, null)
}

/** Get the start/end ISO strings for a given YYYY-MM month */
export function monthBounds(year, month) {
  const start = `${year}-${String(month).padStart(2, '0')}-01`
  const lastDay = new Date(year, month, 0).getDate()
  const end = `${year}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`
  return { start, end }
}

/**
 * Return true if a YYYY-MM-DD date key is an off day.
 * dayOverrides (object keyed by date) takes precedence over the weekday-based offDays array.
 */
export function isOffDay(dk, offDays, dayOverrides = {}) {
  if (dayOverrides[dk] === 'work') return false
  if (dayOverrides[dk] === 'off')  return true
  if (!offDays || offDays.length === 0) return false
  return offDays.includes(new Date(dk + 'T12:00:00').getDay())
}

/** All unique YYYY-MM-DD keys in the log array that fall within the given month */
export function loggedDaysInMonth(logs, year, month) {
  const { start, end } = monthBounds(year, month)
  const keys = new Set()
  for (const l of logs) {
    if (l.date_key >= start && l.date_key <= end) keys.add(l.date_key)
  }
  return [...keys].sort()
}

/**
 * Compute cumulative OT for a month.
 * Only days that have at least one log and are <= today count.
 * Off days (by day-of-week) count all logged hours as pure OT (no required deduction).
 *
 * @param {boolean} includeToday - If false, today's still-in-progress OT is excluded so
 *   the total only reflects fully completed days. Defaults to true.
 */
export function monthCumulativeOtMs(logs, year, month, requiredHoursPerDay, offDays = [], dayOverrides = {}, includeToday = true) {
  const reqMs = requiredHoursPerDay * 3_600_000
  const todayKey = dateKey()
  const days = loggedDaysInMonth(logs, year, month).filter(k => includeToday ? k <= todayKey : k < todayKey)
  let total = 0
  for (const dk of days) {
    const dayLogs = logs.filter(l => l.date_key === dk).sort(byTs)
    const net = computeNetMs(dayLogs, dk === todayKey ? new Date() : null)
    total += isOffDay(dk, offDays, dayOverrides) ? net : net - reqMs
  }
  return total
}

/** Sort comparator by timestamp ascending */
export function byTs(a, b) {
  return new Date(a.timestamp) - new Date(b.timestamp)
}
