// Runs the Excel merge/generate/parse-header logic entirely client-side via
// Pyodide (WebAssembly CPython) — no server needed, works on static hosting
// (GitHub Pages). xlrd/xlwt/xlutils are pure-Python, so report_core.py and
// web_bridge.py run completely unchanged in the browser: real xlwt writes
// real .xls, real xlrd auto-detects the uploaded file's actual styling,
// exactly like the local Python CLI scripts do.
//
// Loaded from the public jsdelivr CDN (Pyodide's official distribution) so
// there's no bundler-vs-WASM friction and the (few-MB) runtime is shared
// across sites' browser caches. Keep PYODIDE_VERSION in sync with the
// `pyodide` devDependency version in package.json.

const PYODIDE_VERSION = '314.0.3'
const PYODIDE_CDN_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`

let pyodidePromise = null
let pyodideReady = false

/** True once Pyodide has finished loading at least once in this session —
 * lets callers decide whether to show a "one-time setup" message. */
export function isPyodideReady() {
  return pyodideReady
}

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

  pyodideReady = true
  return pyodide
}

function getPyodide() {
  if (!pyodidePromise) pyodidePromise = initPyodide()
  return pyodidePromise
}

/** Optionally call ahead of time (e.g. as soon as the Excel card mounts) to
 * start the one-time download/init early, so the first real click feels
 * faster. Safe to call redundantly — errors surface on the real calls. */
export function warmUpPyodide() {
  getPyodide().catch(() => {})
}

export async function mergeXls(xlsBytes, logs, colorHomeHours, dayOverrides, fillMissingOffice) {
  const pyodide = await getPyodide()
  const webBridge = pyodide.pyimport('web_bridge')
  const resultBytes = webBridge.run_merge(
    xlsBytes,
    JSON.stringify(logs),
    !!colorHomeHours,
    dayOverrides ? JSON.stringify(dayOverrides) : null,
    fillMissingOffice !== false,
  )
  return new Blob([resultBytes.toJs()], { type: 'application/vnd.ms-excel' })
}

export async function generateXls(config, logs) {
  const pyodide = await getPyodide()
  const webBridge = pyodide.pyimport('web_bridge')
  const resultBytes = webBridge.run_generate(JSON.stringify(config), JSON.stringify(logs))
  return new Blob([resultBytes.toJs()], { type: 'application/vnd.ms-excel' })
}

export async function parseXlsHeader(xlsBytes) {
  const pyodide = await getPyodide()
  const webBridge = pyodide.pyimport('web_bridge')
  const resultJson = webBridge.run_parse_header(xlsBytes)
  return JSON.parse(resultJson)
}
