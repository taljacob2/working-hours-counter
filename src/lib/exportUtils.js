import { Capacitor, registerPlugin } from '@capacitor/core'

const HE = {
  headers:  { id: 'מזהה', date_key: 'תאריך', timestamp: 'תאריך ושעה', platform: 'מיקום', action: 'פעולה', created_at: 'נוצר בתאריך', note: 'הערה' },
  platform: { office: 'משרד', home: 'בית' },
  action:   { resume: 'כניסה', pause: 'יציאה' },
}

const FileSaver = Capacitor.isNativePlatform() ? registerPlugin('FileSaver') : null

// Chunked to avoid blowing the call stack via String.fromCharCode.apply on large files.
function bytesToBase64(bytes) {
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize))
  }
  return btoa(binary)
}

// On Android shows a native "Save to…" folder picker via ACTION_CREATE_DOCUMENT, so
// the user always knows where the file went. On web, uses the File System Access API
// (showSaveFilePicker) where available so desktop Chrome/Edge users get the same
// "choose a location" prompt; falls back to the classic anchor-download trick
// (silent save to the browser's default downloads folder) on browsers that lack it,
// e.g. Safari/Firefox, or when the picker errors for a reason other than user cancel.
// `content` may be a string (text files) or a Blob/Uint8Array (binary files, e.g.
// .xls) — binary content is base64-encoded for the native bridge.
export async function saveFile(content, filename, mimeType) {
  const isBinary = content instanceof Blob || content instanceof Uint8Array
  if (FileSaver) {
    if (isBinary) {
      const bytes = content instanceof Blob ? new Uint8Array(await content.arrayBuffer()) : content
      await FileSaver.saveFile({ content: bytesToBase64(bytes), filename, mimeType, isBase64: true })
    } else {
      await FileSaver.saveFile({ content, filename, mimeType })
    }
  } else {
    const blob = content instanceof Blob ? content : new Blob([content], { type: mimeType })

    if (window.showSaveFilePicker) {
      try {
        const ext = filename.includes('.') ? '.' + filename.split('.').pop() : ''
        const handle = await window.showSaveFilePicker({
          suggestedName: filename,
          types: ext ? [{ description: mimeType, accept: { [mimeType]: [ext] } }] : undefined,
        })
        const writable = await handle.createWritable()
        await writable.write(blob)
        await writable.close()
        return
      } catch (err) {
        if (err?.name === 'AbortError') throw new Error('cancelled')
        // Any other failure (unsupported context, permission denial, etc.) — fall
        // through to the classic download below instead of failing the export.
      }
    }

    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }
}

export async function exportCsv(logs, filename = 'work-logs.csv', use24Hour = true, compact = false, hebrew = false) {
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
  await saveFile('﻿' + csv, filename, 'text/csv;charset=utf-8;')
}
