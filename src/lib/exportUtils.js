export function exportCsv(logs, filename = 'work-logs.csv') {
  const cols = ['id', 'date_key', 'timestamp', 'platform', 'action', 'created_at', 'note']
  const header = cols.join(',')
  const rows = logs.map(l =>
    cols.map(c => {
      const v = l[c] ?? ''
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
