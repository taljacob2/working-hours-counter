const HE = {
  headers:  { id: 'מזהה', date_key: 'תאריך', timestamp: 'תאריך ושעה', platform: 'מיקום', action: 'פעולה', created_at: 'נוצר בתאריך', note: 'הערה' },
  platform: { office: 'משרד', home: 'בית' },
  action:   { resume: 'כניסה', pause: 'יציאה' },
}

export function exportCsv(logs, filename = 'work-logs.csv', use24Hour = true, compact = false, hebrew = false) {
  const cols = compact
    ? ['timestamp', 'platform', 'action']
    : ['id', 'date_key', 'timestamp', 'platform', 'action', 'created_at', 'note']
  const headerCols = hebrew ? cols.map(c => HE.headers[c] ?? c) : cols
  const header = headerCols.map(h => `"${h}"`).join(',')
  const rows = logs.map(l =>
    cols.map(c => {
      let v = l[c] ?? ''
      if ((c === 'timestamp' || c === 'created_at') && v) {
        v = new Date(v).toLocaleString([], { hour12: !use24Hour })
      }
      if (hebrew && HE[c]) v = HE[c][v] ?? v
      return `"${String(v).replace(/"/g, '""')}"`
    }).join(',')
  )
  const csv = [header, ...rows].join('\n')
  const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
