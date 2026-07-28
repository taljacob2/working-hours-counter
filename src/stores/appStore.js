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
// Max rebalance history entries per month kept in Supabase. 0 = unlimited.
export const rebalHistoryCap = writable(0)
// Per-date overrides: { 'YYYY-MM-DD': 'work' | 'off' }. Takes precedence over offDays.
export const dayOverrides = writable({})

// ── Office geofence ───────────────────────────────────────────
// List of saved locations: [{ id, name, lat, lng, radiusMeters }]
export const officeLocations = writable([])
// ID of the currently active location (null = none)
export const activeOfficeId = writable(null)
// Derived single location — keeps existing geofence code in App.svelte unchanged
export const officeLocation = derived([officeLocations, activeOfficeId], ([$locs, $id]) =>
  $locs.find(l => l.id === $id) ?? null
)
// Whether auto resume/pause via geofence is active
export const autoTrackEnabled = writable(false)

// ── Notifications ─────────────────────────────────────────────
export const notifMorningEnabled = writable(false)
export const notifMorningTime    = writable('09:00')
export const notifEveningEnabled = writable(false)
export const notifEveningTime    = writable('19:00')
export const notifTargetEnabled  = writable(false)
// null = use requiredHours; number = custom hours override
export const notifTargetHoursOverride = writable(null)

// ── Excel merge ───────────────────────────────────────────────
// When true, home-hours intervals are written in a distinct colour in merged XLS files.
export const excelColorHomeHours = writable(false)
// When true, an office session the app recorded but the company's sheet never
// detailed (whole day has no company-provided time entries) is backfilled into a
// free slot in orange, flagging it for HR to confirm. Defaults on.
export const fillMissingOfficeHours = writable(true)

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
