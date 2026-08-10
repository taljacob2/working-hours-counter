// Runs the Excel merge/generate/parse-header logic entirely client-side via
// Pyodide (WebAssembly CPython) — no server needed, works on static hosting
// (GitHub Pages). xlrd/xlwt/xlutils are pure-Python, so report_core.py and
// web_bridge.py run completely unchanged in the browser: real xlwt writes
// real .xls, real xlrd auto-detects the uploaded file's actual styling,
// exactly like the local Python CLI scripts do.
//
// The actual Pyodide runtime lives in src/workers/pyodideWorker.js, off the
// main thread — its init (WASM instantiation, micropip install) is heavy
// enough that running it inline used to freeze the whole page (couldn't
// even open other Settings sections) while it loaded. This file is just the
// main-thread message-passing wrapper; callers see the same async API as
// before and don't know a worker is involved.

import { writable } from 'svelte/store'

let worker = null
let pyodideReady = false
let nextRequestId = 1
const pending = new Map()

/** True once Pyodide has finished loading at least once in this session —
 * lets callers decide whether to show a "one-time setup" message. */
export function isPyodideReady() {
  return pyodideReady
}

// 'idle' | 'loading' | 'ready' | 'error' — lets the Excel Reports section show
// its own loading bar without touching the rest of the Settings screen.
export const pyodideStatus = writable('idle')

function ensureWorker() {
  if (worker) return worker

  worker = new Worker(new URL('../workers/pyodideWorker.js', import.meta.url), { type: 'module' })

  worker.onmessage = e => {
    const msg = e.data
    if (msg.type === 'status') {
      if (msg.status === 'ready') {
        pyodideReady = true
        pyodideStatus.set('ready')
      } else if (msg.status === 'error') {
        pyodideStatus.set('error')
        failAllPending(new Error(msg.message || 'Failed to load the Excel engine'))
        // Let a later call (e.g. an actual button click) retry from scratch
        // instead of forever replaying the same broken worker.
        worker.terminate()
        worker = null
      } else {
        pyodideStatus.set(msg.status)
      }
      return
    }
    const p = pending.get(msg.id)
    if (!p) return
    pending.delete(msg.id)
    if (msg.ok) p.resolve(msg.result)
    else p.reject(new Error(msg.error))
  }

  worker.onerror = err => {
    pyodideStatus.set('error')
    failAllPending(new Error(err.message || 'Excel engine worker crashed'))
    worker?.terminate()
    worker = null
  }

  return worker
}

function failAllPending(err) {
  for (const p of pending.values()) p.reject(err)
  pending.clear()
}

function callWorker(action, args) {
  const w = ensureWorker()
  const id = nextRequestId++
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    w.postMessage({ id, action, args })
  })
}

/** Optionally call ahead of time (e.g. as soon as the Excel card mounts) to
 * start the one-time download/init early, so the first real click feels
 * faster. Safe to call redundantly — errors surface on the real calls. */
export function warmUpPyodide() {
  ensureWorker()
}

export async function mergeXls(xlsBytes, logs, colorHomeHours, dayOverrides, fillMissingOffice) {
  const resultBytes = await callWorker('merge', [
    xlsBytes,
    JSON.stringify(logs),
    !!colorHomeHours,
    dayOverrides ? JSON.stringify(dayOverrides) : null,
    fillMissingOffice !== false,
  ])
  return new Blob([resultBytes], { type: 'application/vnd.ms-excel' })
}

export async function generateXls(config, logs) {
  const resultBytes = await callWorker('generate', [JSON.stringify(config), JSON.stringify(logs)])
  return new Blob([resultBytes], { type: 'application/vnd.ms-excel' })
}

export async function parseXlsHeader(xlsBytes) {
  const resultJson = await callWorker('parseHeader', [xlsBytes])
  return JSON.parse(resultJson)
}
