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

// Capacitor plugin objects are Proxies whose `get` trap returns a callable
// wrapper for ANY property, including `then` — so returning one directly from
// an async function (or otherwise making it a promise's resolution value)
// makes JS treat it as a thenable and call `.then()` on it, which Android
// forwards to native as a real (nonexistent) method call and throws
// "X.then() is not implemented". Wrap it in a plain object so it can safely
// pass through `await`/Promise resolution, then unwrap with a plain property
// access (not a promise step) at each call site.
async function getPlugin() {
  if (!isNative()) return null
  try {
    const { LocalNotifications } = await import('@capacitor/local-notifications')
    return { plugin: LocalNotifications }
  } catch {
    return null
  }
}

/** Ask Android for notification permission. Returns true if granted. */
export async function requestNotificationPermission() {
  const { plugin } = (await getPlugin()) || {}
  if (!plugin) return true  // non-native: allow toggling settings; scheduling is a no-op anyway
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
  deliverVia = 'native',
}) {
  if (deliverVia === 'push') return  // user chose Web Push only — native scheduling would duplicate it
  const { plugin } = (await getPlugin()) || {}
  if (!plugin) return

  // Ensure the notification channel exists on Android (idempotent)
  await plugin.createChannel?.({
    id: 'whl_reminders',
    name: 'Work reminders',
    importance: 3,
    visibility: 1,
    sound: 'default',
    vibration: true,
  }).catch(() => {})

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
  const { plugin } = (await getPlugin()) || {}
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
  const { plugin } = (await getPlugin()) || {}
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
  const { plugin } = (await getPlugin()) || {}
  if (!plugin) return
  await plugin.cancel({ notifications: [{ id: ID_TARGET }] }).catch(() => {})
}

// ── Web Push (installed PWA, non-native) ──────────────────────
// Actual scheduling/sending happens server-side (scripts/send-notifications.mjs,
// run on a GitHub Actions cron) since no browser can wake up and fire a future
// local notification on its own. This section only manages the subscription —
// telling the server "here's a device that wants pushes."

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = atob(base64)
  return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)))
}

/**
 * True only when Web Push can actually work here: iOS (and most browsers)
 * only expose these APIs to an installed/standalone app, not a regular tab.
 */
export function isPushSupported() {
  if (typeof window === 'undefined' || isNative()) return false
  const standalone = window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window && standalone
}

/** 'unsupported' | 'denied' | 'subscribed' | 'not-subscribed' */
export async function getPushSubscriptionStatus() {
  if (!isPushSupported()) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  const registration = await navigator.serviceWorker.getRegistration()
  const subscription = await registration?.pushManager.getSubscription()
  return subscription ? 'subscribed' : 'not-subscribed'
}

/** Request permission, subscribe this device, and store the subscription in Supabase. */
export async function subscribeToPush(sb) {
  if (!isPushSupported()) return false
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return false

  const vapidKey = import.meta.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY
  if (!vapidKey) { console.warn('[Push] Missing NEXT_PUBLIC_VAPID_PUBLIC_KEY'); return false }

  const registration = await navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`)
  await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidKey),
  })
  const json = subscription.toJSON()
  // user_id must be explicit, not left to the column default: on an upsert
  // conflict (same device re-subscribing under a different account),
  // PostgREST only updates columns present in the payload, so a bare
  // default(auth.uid()) would only ever take effect on first insert.
  const { data: { user } } = await sb.auth.getUser()
  const { error } = await sb.from('push_subscriptions').upsert([{
    endpoint: json.endpoint,
    p256dh: json.keys.p256dh,
    auth: json.keys.auth,
    user_id: user.id,
  }], { onConflict: 'endpoint' })
  if (error) console.warn('[Push] Failed to store subscription:', error)
  return !error
}

/** Unsubscribe this device and remove its stored subscription. */
export async function unsubscribeFromPush(sb) {
  if (!('serviceWorker' in navigator)) return
  const registration = await navigator.serviceWorker.getRegistration()
  const subscription = await registration?.pushManager.getSubscription()
  if (!subscription) return
  const endpoint = subscription.endpoint
  await subscription.unsubscribe()
  await sb.from('push_subscriptions').delete().eq('endpoint', endpoint)
}
