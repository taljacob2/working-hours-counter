// Sends Web Push reminders (morning check-in, evening nudge, daily target
// reached) to any subscribed installed PWA/browser. Run on a schedule via
// .github/workflows/notification-scheduler.yml — no browser can wake up and
// fire a future local notification on its own, so this script is the
// server-side equivalent of what @capacitor/local-notifications does
// natively on Android (src/lib/notifications.js).
//
// Designed to be safe to run every few minutes and to self-heal after a
// missed run: every check is "should this have fired by now and hasn't been
// sent today/for this span yet?", not "is it exactly the target time right
// now?" — so a late or skipped run just sends slightly late next time,
// rather than losing the reminder entirely.

import { createClient } from '@supabase/supabase-js'
import webpush from 'web-push'
import { isOffDay } from '../src/lib/timeUtils.js'

const {
  SUPABASE_URL,
  SUPABASE_SERVICE_ROLE_KEY,
  VAPID_PUBLIC_KEY,
  VAPID_PRIVATE_KEY,
  VAPID_CONTACT_EMAIL = 'taljacob2@gmail.com',
  NOTIF_TIMEZONE = 'UTC',
} = process.env

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY || !VAPID_PUBLIC_KEY || !VAPID_PRIVATE_KEY) {
  console.error('Missing required env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY')
  process.exit(1)
}

webpush.setVapidDetails(`mailto:${VAPID_CONTACT_EMAIL}`, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY)
const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

// The Actions runner's system clock is UTC, but reminder times ('09:00' etc.)
// and the work_logs date_key the client writes are the user's local time —
// so "today" and "is it past the reminder time" both need computing against
// NOTIF_TIMEZONE explicitly, not the runner's own timezone.
function localParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: NOTIF_TIMEZONE,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(date)
  const get = t => parts.find(p => p.type === t).value
  return { dateKey: `${get('year')}-${get('month')}-${get('day')}`, hour: Number(get('hour')), minute: Number(get('minute')) }
}

function pastOrAt(hour, minute, targetHHMM) {
  const [th, tm] = (targetHHMM || '00:00').split(':').map(Number)
  return hour > th || (hour === th && minute >= tm)
}

async function main() {
  const now = new Date()
  const { dateKey: today, hour, minute } = localParts(now)

  const { data: settingsRows, error: settingsErr } = await sb.from('work_settings').select('key, value')
  if (settingsErr) throw settingsErr
  const s = Object.fromEntries((settingsRows || []).map(r => [r.key, r.value]))

  const deliverVia = s.notifDeliverVia || 'both'
  if (deliverVia === 'native') { console.log('notifDeliverVia=native — nothing to do here'); return }

  const { data: subs, error: subsErr } = await sb.from('push_subscriptions').select('*')
  if (subsErr) throw subsErr
  if (!subs || subs.length === 0) { console.log('No push subscriptions registered — nothing to do'); return }

  const offDaysArr = JSON.parse(s.offDays || '[0,6]')
  const dayOverridesObj = JSON.parse(s.dayOverrides || '{}')
  const requiredDailyHours = parseFloat(s.requiredDailyHours || '9')
  const todaysOff = isOffDay(today, offDaysArr, dayOverridesObj)

  const { data: todaysLogs, error: logsErr } = await sb
    .from('work_logs').select('*').eq('date_key', today).order('timestamp', { ascending: true })
  if (logsErr) throw logsErr
  const hasAnyLogToday = (todaysLogs || []).length > 0

  const toSend = []

  if (s.notifMorningEnabled === 'true' && !todaysOff && !hasAnyLogToday &&
      pastOrAt(hour, minute, s.notifMorningTime || '09:00') && s.pushLastSentMorning !== today) {
    toSend.push({ marker: 'pushLastSentMorning', value: today, title: 'Working Hours', body: "Haven't clocked in yet — working today?" })
  }

  if (s.notifEveningEnabled === 'true' && !todaysOff && !hasAnyLogToday &&
      pastOrAt(hour, minute, s.notifEveningTime || '19:00') && s.pushLastSentEvening !== today) {
    toSend.push({ marker: 'pushLastSentEvening', value: today, title: 'Working Hours', body: "You haven't logged any work today." })
  }

  if (s.notifTargetEnabled === 'true') {
    const lastLog = (todaysLogs || [])[todaysLogs.length - 1]
    if (lastLog && lastLog.action === 'resume') {
      const targetHoursOverride = s.notifTargetHoursOverride ? parseFloat(s.notifTargetHoursOverride) : null
      const targetMs = (targetHoursOverride ?? requiredDailyHours) * 3_600_000
      const elapsedMs = now.getTime() - new Date(lastLog.timestamp).getTime()
      if (elapsedMs >= targetMs && s.pushLastSentTargetForResumeAt !== lastLog.timestamp) {
        toSend.push({
          marker: 'pushLastSentTargetForResumeAt', value: lastLog.timestamp,
          title: 'Working Hours', body: "You've reached your daily target — consider clocking out.",
        })
      }
    }
  }

  if (toSend.length === 0) { console.log('Nothing to send this run'); return }

  for (const item of toSend) {
    let anySent = false
    for (const sub of subs) {
      const pushSubscription = { endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } }
      try {
        await webpush.sendNotification(pushSubscription, JSON.stringify({ title: item.title, body: item.body }))
        anySent = true
        console.log(`Sent "${item.title}" to subscription ${sub.id}`)
      } catch (err) {
        if (err.statusCode === 404 || err.statusCode === 410) {
          console.log(`Subscription ${sub.id} is gone (${err.statusCode}) — removing it`)
          await sb.from('push_subscriptions').delete().eq('id', sub.id)
        } else {
          console.warn(`Send failed for subscription ${sub.id} (status ${err.statusCode}):`, err.message)
        }
      }
    }
    // Only mark as sent if it actually reached at least one device — if every
    // send failed (all stale), leave the marker unset so the next run retries.
    if (anySent) {
      const { error } = await sb.from('work_settings').upsert([{ key: item.marker, value: item.value }])
      if (error) console.warn(`Failed to record marker ${item.marker}:`, error.message)
    }
  }
}

main().catch(err => { console.error(err); process.exit(1) })
