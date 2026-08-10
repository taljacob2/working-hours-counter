// Minimal service worker: exists only to receive Web Push events for the
// installed PWA (iOS requires one registered before push will work at all)
// and to focus/open the app when a notification is tapped. No offline
// caching — that's a separate concern this doesn't attempt to solve.

self.addEventListener('push', event => {
  let data = { title: 'Working Hours', body: '' }
  try { data = event.data.json() } catch { /* keep default */ }

  event.waitUntil(
    self.registration.showNotification(data.title || 'Working Hours', {
      body: data.body || '',
      icon: 'icon-192.png',
      badge: 'icon-192.png',
    })
  )
})

self.addEventListener('notificationclick', event => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientsArr => {
      const existing = clientsArr.find(c => 'focus' in c)
      if (existing) return existing.focus()
      return self.clients.openWindow('./')
    })
  )
})
