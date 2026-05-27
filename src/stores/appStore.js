import { writable, derived } from 'svelte/store'

// ── Auth / setup ──────────────────────────────────────────────
export const screen = writable('loading') // 'loading' | 'config' | 'signin' | 'main' | 'logs' | 'settings'
export const user = writable(null)

// ── Data ──────────────────────────────────────────────────────
export const logs = writable([])
export const requiredHours = writable(9)
export const minimumDailyHours = writable(5)
export const maximumDailyHours = writable(12)
export const commuteGapMinutes = writable(45)
export const use24HourFormat = writable(true)
// Days of week that are off (0=Sun, 1=Mon, ..., 6=Sat). Default: Sat+Sun.
export const offDays = writable([0, 6])
// Per-date overrides: { 'YYYY-MM-DD': 'work' | 'off' }. Takes precedence over offDays.
export const dayOverrides = writable({})

// ── Office geofence ───────────────────────────────────────────
// null = not configured; { lat, lng, radiusMeters }
export const officeLocation = writable(null)
// Whether auto resume/pause via geofence is active
export const autoTrackEnabled = writable(false)

// ── UI state ──────────────────────────────────────────────────
export const theme = writable('light')
export const toasts = writable([])
export const loading = writable(false)

// Calendar cursor (first day of displayed month)
export const calCursor = writable(new Date(new Date().getFullYear(), new Date().getMonth(), 1))
export const selectedDate = writable(todayKey())
export const logResolution = writable('compact') // 'compact' | 'full'
export const editingLogId = writable(null)

// ── Helpers ───────────────────────────────────────────────────
function todayKey() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

// Derived: logs for selected date, sorted by timestamp
export const selectedDayLogs = derived([logs, selectedDate], ([$logs, $sel]) =>
  $logs.filter(l => l.date_key === $sel).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
)

// ── Toast helpers ─────────────────────────────────────────────
let toastId = 0
export function showToast(message, type = 'info') {
  const id = ++toastId
  toasts.update(t => [...t, { id, message, type }])
  setTimeout(() => toasts.update(t => t.filter(x => x.id !== id)), 2800)
}
