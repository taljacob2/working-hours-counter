// Shared by ExcelMergeButton and GenerateReportButton so both build the same
// { date, start, end, platform } intervals from raw resume/pause logs.

/** Format local Date to HH:MM (24h) */
export function formatLocalHM(tsStr) {
  const d = new Date(tsStr)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

/** Pair resume/pause events into { date, start, end, platform } intervals for one platform */
export function buildIntervalsForPlatform(monthLogs, platform) {
  const sortedLogs = monthLogs
    .filter(l => l.platform === platform)
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))

  const intervals = []
  const dayGroups = {}
  for (const log of sortedLogs) {
    if (!dayGroups[log.date_key]) dayGroups[log.date_key] = []
    dayGroups[log.date_key].push(log)
  }

  for (const [dateKey, dayLogs] of Object.entries(dayGroups)) {
    let openResume = null
    for (const log of dayLogs) {
      if (log.action === 'resume') {
        openResume = log
      } else if (log.action === 'pause' && openResume) {
        intervals.push({
          date: dateKey,
          start: formatLocalHM(openResume.timestamp),
          end: formatLocalHM(log.timestamp),
          platform
        })
        openResume = null
      }
    }
  }
  return intervals
}

/** Filter logs to one calendar month and build both-platform intervals */
export function monthLogsAndIntervals(allLogs, year, month) {
  const prefix = `${year}-${String(month).padStart(2, '0')}`
  const monthLogs = allLogs.filter(l => l.date_key.startsWith(prefix))
  return [...buildIntervalsForPlatform(monthLogs, 'home'), ...buildIntervalsForPlatform(monthLogs, 'office')]
}
