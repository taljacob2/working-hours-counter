// Copies the Python modules needed by the in-browser Pyodide bridge into
// public/py/, so Vite serves them as static assets. Repo root stays the
// single source of truth (also where the CLI scripts import from) — this
// script just keeps public/py/ in sync with it before dev/build.
import { copyFileSync, mkdirSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const rootDir = dirname(dirname(fileURLToPath(import.meta.url)))
const destDir = join(rootDir, 'public', 'py')

mkdirSync(destDir, { recursive: true })

for (const name of ['report_core.py', 'web_bridge.py']) {
  copyFileSync(join(rootDir, name), join(destDir, name))
  console.log(`Synced ${name} -> public/py/${name}`)
}
