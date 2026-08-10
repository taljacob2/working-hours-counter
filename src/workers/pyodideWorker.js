// Runs Pyodide (WebAssembly CPython) in a dedicated worker so its heavy,
// mostly-synchronous init (WASM instantiation, micropip dependency install,
// Python bytecode compilation) never blocks the main thread — otherwise the
// whole page's UI (clicks, other Settings sections, etc.) freezes for the
// ~3s it takes to come up, even though the loading itself is "async" from
// JS's point of view. See src/lib/pyodideBridge.js for the main-thread side
// of this — it owns the message-passing wrapper so callers never know a
// worker is involved.

const PYODIDE_VERSION = '314.0.3'
const PYODIDE_CDN_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`

let webBridge = null
let initPromise = null

async function initPyodide() {
  const { loadPyodide } = await import(/* @vite-ignore */ `${PYODIDE_CDN_BASE}pyodide.mjs`)
  const pyodide = await loadPyodide({ indexURL: PYODIDE_CDN_BASE })

  await pyodide.loadPackage('micropip')
  const micropip = pyodide.pyimport('micropip')
  // Pinned to match requirements.txt — same versions the local CLI uses.
  await micropip.install(['xlrd==2.0.2', 'xlwt==1.3.0', 'xlutils==2.0.0'])

  const base = import.meta.env.BASE_URL
  const [reportCoreSrc, webBridgeSrc] = await Promise.all([
    fetch(`${base}py/report_core.py`).then(r => r.text()),
    fetch(`${base}py/web_bridge.py`).then(r => r.text()),
  ])
  pyodide.FS.writeFile('/report_core.py', reportCoreSrc)
  pyodide.FS.writeFile('/web_bridge.py', webBridgeSrc)
  pyodide.runPython(`
import sys
if '/' not in sys.path:
    sys.path.insert(0, '/')
import web_bridge
`)

  webBridge = pyodide.pyimport('web_bridge')
}

function ensureInit() {
  if (!initPromise) {
    initPromise = initPyodide().then(
      () => self.postMessage({ type: 'status', status: 'ready' }),
      err => {
        self.postMessage({ type: 'status', status: 'error', message: String(err?.message || err) })
        throw err
      }
    )
  }
  return initPromise
}

self.postMessage({ type: 'status', status: 'loading' })
ensureInit()

self.onmessage = async e => {
  const { id, action, args } = e.data
  try {
    await ensureInit()
    let result
    if (action === 'merge') {
      const [xlsBytes, logsJsonStr, colorHomeHours, dayOverridesJsonStr, fillMissingOffice] = args
      result = webBridge.run_merge(xlsBytes, logsJsonStr, colorHomeHours, dayOverridesJsonStr, fillMissingOffice).toJs()
    } else if (action === 'generate') {
      const [configJsonStr, logsJsonStr] = args
      result = webBridge.run_generate(configJsonStr, logsJsonStr).toJs()
    } else if (action === 'parseHeader') {
      const [xlsBytes] = args
      result = webBridge.run_parse_header(xlsBytes)
    } else {
      throw new Error(`Unknown action: ${action}`)
    }
    self.postMessage({ id, ok: true, result })
  } catch (err) {
    self.postMessage({ id, ok: false, error: String(err?.message || err) })
  }
}
