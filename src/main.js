import './app.css'
import App from './App.svelte'
import { mount } from 'svelte'

const app = mount(App, { target: document.getElementById('app') })

// Needed for Web Push (public/sw.js) — no-op on native, where local
// notifications are scheduled directly by the OS instead.
if (!window.Capacitor?.isNativePlatform?.() && 'serviceWorker' in navigator) {
  navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(console.warn)
}

export default app
