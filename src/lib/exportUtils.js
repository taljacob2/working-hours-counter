export function exportCsv(logs, filename = 'work-logs.csv', use24Hour = true) {
  const cols = ['id', 'date_key', 'timestamp', 'platform', 'action', 'created_at', 'note']
  const header = cols.join(',')
  const rows = logs.map(l =>
    cols.map(c => {
      let v = l[c] ?? ''
      if ((c === 'timestamp' || c === 'created_at') && v) {
        // Convert the UTC string to a human-readable local time format
        v = new Date(v).toLocaleString([], { hour12: !use24Hour })
      }
      return `"${String(v).replace(/"/g, '""')}"`
    }).join(',')
  )
  const csv = [header, ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
