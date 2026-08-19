import { writable, derived } from 'svelte/store'

const deferredPrompt = writable(null)
export const canInstall = derived(deferredPrompt, $e => $e !== null)

let registered = false
export function initInstallPrompt() {
  if (registered) return
  registered = true
  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault()
    deferredPrompt.set(e)
  })
  window.addEventListener('appinstalled', () => deferredPrompt.set(null))
}

export async function promptInstall() {
  let event
  deferredPrompt.update(e => { event = e; return null })
  if (!event) return false
  event.prompt()
  const choice = await event.userChoice
  return choice.outcome === 'accepted'
}

export function isIOS() {
  const ua = navigator.userAgent
  const isIOSUA = /iPad|iPhone|iPod/.test(ua)
  // iPadOS 13+ Safari reports its UA as "Macintosh" — disambiguate via touch support.
  const isIPadOS = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1
  return isIOSUA || isIPadOS
}

export function isStandalone() {
  return window.navigator.standalone === true ||
    window.matchMedia('(display-mode: standalone)').matches
}
