/**
 * GeoFenceWatcher
 *
 * Monitors whether the user is inside/outside the configured office location
 * and fires onEnter / onLeave callbacks accordingly.
 *
 * On native (Capacitor Android): uses @capgo/background-geolocation, which
 * works even when the app is backgrounded or the screen is off.
 *
 * On web (browser): uses navigator.geolocation.watchPosition as a fallback.
 * This only works while the browser tab is open and visible.
 */

// Haversine distance in metres between two lat/lng points
function haversineMetres(lat1, lng1, lat2, lng2) {
  const R = 6_371_000
  const toRad = d => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

// Detect Capacitor native environment
function isNative() {
  return typeof window !== 'undefined' && !!(window.Capacitor?.isNativePlatform?.())
}

export class GeoFenceWatcher {
  #location       // { lat, lng, radiusMeters }
  #onEnter        // () => void
  #onLeave        // () => void
  #insideOffice = null   // null=unknown, true=inside, false=outside
  #watchId = null       // web watchPosition ID
  #nativePlugin = null  // @capgo/background-geolocation plugin ref
  #hysteresisTimer = null
  #HYSTERESIS_MS = 30_000  // must be inside/outside for 30s before firing

  constructor({ location, onEnter, onLeave }) {
    this.#location = location
    this.#onEnter = onEnter
    this.#onLeave = onLeave
  }

  async start() {
    if (isNative()) {
      await this.#startNative()
    } else {
      this.#startWeb()
    }
  }

  stop() {
    if (this.#hysteresisTimer) { clearTimeout(this.#hysteresisTimer); this.#hysteresisTimer = null }
    if (this.#nativePlugin) {
      this.#nativePlugin.removeAllListeners?.()
      this.#nativePlugin.stopBackgroundTask?.()
      this.#nativePlugin = null
    }
    if (this.#watchId !== null && typeof navigator !== 'undefined') {
      navigator.geolocation.clearWatch(this.#watchId)
      this.#watchId = null
    }
  }

  updateLocation(location) {
    this.#location = location
    this.#insideOffice = null  // reset state — next position update will re-evaluate
  }

  // ── Native (Capacitor background geolocation) ─────────────────
  async #startNative() {
    try {
      const { BackgroundGeolocation } = await import('@capgo/background-geolocation')
      this.#nativePlugin = BackgroundGeolocation

      await BackgroundGeolocation.addWatcher(
        {
          backgroundMessage: 'Working Hours is tracking your office location.',
          backgroundTitle: 'Office Auto-Track',
          requestPermissions: true,
          stale: false,
          distanceFilter: 15,  // only fire updates every 15m movement
        },
        (position, error) => {
          if (error || !position) return
          this.#handlePosition(position.latitude, position.longitude)
        }
      )
    } catch (e) {
      console.warn('[GeoFence] Native plugin unavailable, falling back to web:', e)
      this.#startWeb()
    }
  }

  // ── Web fallback (foreground only) ────────────────────────────
  #startWeb() {
    if (!navigator?.geolocation) return
    this.#watchId = navigator.geolocation.watchPosition(
      pos => this.#handlePosition(pos.coords.latitude, pos.coords.longitude),
      err => console.warn('[GeoFence] Web geolocation error:', err),
      { enableHighAccuracy: true, maximumAge: 15_000 }
    )
  }

  // ── Shared position handler ───────────────────────────────────
  #handlePosition(lat, lng) {
    if (!this.#location) return
    const dist = haversineMetres(lat, lng, this.#location.lat, this.#location.lng)
    const nowInside = dist <= this.#location.radiusMeters

    if (nowInside === this.#insideOffice) {
      // No boundary crossing — cancel any pending hysteresis timer
      if (this.#hysteresisTimer) { clearTimeout(this.#hysteresisTimer); this.#hysteresisTimer = null }
      return
    }

    // Boundary crossing detected — start hysteresis timer
    if (this.#hysteresisTimer) clearTimeout(this.#hysteresisTimer)
    this.#hysteresisTimer = setTimeout(() => {
      this.#hysteresisTimer = null
      this.#insideOffice = nowInside
      if (nowInside) this.#onEnter()
      else           this.#onLeave()
    }, this.#HYSTERESIS_MS)
  }
}
