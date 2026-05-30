/**
 * Notification scheduler for Working Hours.
 * Wraps @capacitor/local-notifications with safe no-ops on web.
 *
 * Notification IDs (stable across reschedules):
 *   100–106  morning check-in reminders  (today+0 … today+6)
 *   200–206  evening no-log nudges       (today+0 … today+6)
 *   300      daily target reached        (single, overwritten each resume)
 */

import { isOffDay, dateKey } from './timeUtils.js'

const ID_MORNING_BASE = 100
const ID_EVENING_BASE = 200
const ID_TARGET       = 300
const LOOKAHEAD_DAYS  = 7

function isNative() {
  return typeof window !== 'undefined' && !!(window.Capacitor?.isNativePlatform?.())
}

async function getPlugin() {
  if (!isNative()) return null
  try {
    const { LocalNotifications } = await import('@capacitor/local-notifications')
    return LocalNotifications
  } catch {
    return null
  }
}

/** Ask Android for notification permission. Returns true if granted. */
export async function requestNotificationPermission() {
  const plugin = await getPlugin()
  if (!plugin) return false
  try {
    const { display } = await plugin.requestPermissions()
    return display === 'granted'
  } catch {
    return false
  }
}

/**
 * Cancel all managed notifications then reschedule based on current settings.
 * Call on app mount (after settings loaded) and whenever settings change.
 */
export async function rescheduleAll({
  morningEnabled, morningTime,
  eveningEnabled, eveningTime,
  offDaysArr, dayOverridesObj,
}) {
  const plugin = await getPlugin()
  if (!plugin) return

  const allIds = [
    ...Array.from({ length: LOOKAHEAD_DAYS }, (_, i) => ({ id: ID_MORNING_BASE + i })),
    ...Array.from({ length: LOOKAHEAD_DAYS }, (_, i) => ({ id: ID_EVENING_BASE + i })),
    { id: ID_TARGET },
  ]
  await plugin.cancel({ notifications: allIds }).catch(() => {})

  const notifications = []
  const now = new Date()

  if (morningEnabled && morningTime) {
    const [mh, mm] = morningTime.split(':').map(Number)
    for (let i = 0; i < LOOKAHEAD_DAYS; i++) {
      const d = new Date(now)
      d.setDate(now.getDate() + i)
      const dk = dateKey(d)
      if (isOffDay(dk, offDaysArr, dayOverridesObj)) continue
      const at = new Date(d)
      at.setHours(mh, mm, 0, 0)
      if (at <= now) continue
      notifications.push({
        id: ID_MORNING_BASE + i,
        title: 'Working Hours',
        body: "Haven't clocked in yet — working today?",
        schedule: { at },
        smallIcon: 'ic_stat_icon_config_sample',
        channelId: 'whl_reminders',
      })
    }
  }

  if (eveningEnabled && eveningTime) {
    const [eh, em] = eveningTime.split(':').map(Number)
    for (let i = 0; i < LOOKAHEAD_DAYS; i++) {
      const d = new Date(now)
      d.setDate(now.getDate() + i)
      const dk = dateKey(d)
      if (isOffDay(dk, offDaysArr, dayOverridesObj)) continue
      const at = new Date(d)
      at.setHours(eh, em, 0, 0)
      if (at <= now) continue
      notifications.push({
        id: ID_EVENING_BASE + i,
        title: 'Working Hours',
        body: "You haven't logged any work today.",
        schedule: { at },
        smallIcon: 'ic_stat_icon_config_sample',
        channelId: 'whl_reminders',
      })
    }
  }

  if (notifications.length > 0) {
    await plugin.schedule({ notifications }).catch(console.warn)
  }
}

/**
 * Cancel today's morning (ID 100) and evening (ID 200) reminders.
 * Call as soon as the user creates any log for today.
 */
export async function cancelTodayReminders() {
  const plugin = await getPlugin()
  if (!plugin) return
  await plugin.cancel({
    notifications: [{ id: ID_MORNING_BASE }, { id: ID_EVENING_BASE }],
  }).catch(() => {})
}

/**
 * Schedule the "daily target reached" notification.
 * Call when a resume log is created (if the feature is enabled).
 * @param {Date}   resumeTime       — when the user clocked in
 * @param {number} requiredHoursMs  — ms until target (e.g. 9 * 3_600_000)
 */
export async function scheduleTargetReached(resumeTime, requiredHoursMs) {
  const plugin = await getPlugin()
  if (!plugin) return
  await plugin.cancel({ notifications: [{ id: ID_TARGET }] }).catch(() => {})
  const at = new Date(resumeTime.getTime() + requiredHoursMs)
  if (at <= new Date()) return
  await plugin.schedule({
    notifications: [{
      id: ID_TARGET,
      title: 'Working Hours',
      body: "You've reached your daily target — consider clocking out.",
      schedule: { at },
      smallIcon: 'ic_stat_icon_config_sample',
      channelId: 'whl_reminders',
    }],
  }).catch(console.warn)
}

/** Cancel the pending "daily target reached" notification. */
export async function cancelTargetReached() {
  const plugin = await getPlugin()
  if (!plugin) return
  await plugin.cancel({ notifications: [{ id: ID_TARGET }] }).catch(() => {})
}
