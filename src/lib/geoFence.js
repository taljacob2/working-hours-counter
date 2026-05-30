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
  #insideOffice = null    // confirmed state: null=unknown, true=inside, false=outside
  #pendingInside = null   // transition being waited on (null = none)
  #pendingCrossedAt = null // wall-clock time when the current pending transition started
  #watchId = null         // web watchPosition ID
  #nativePlugin = null    // @capgo/background-geolocation plugin ref
  #nativeWatcherId = null // watcher ID returned by addWatcher, needed for removeWatcher
  #hysteresisTimer = null
  #enterThresholdMs       // ms inside required before onEnter fires
  #leaveThresholdMs       // ms outside required before onLeave fires

  constructor({ location, onEnter, onLeave, enterThresholdMs = 7_200_000, leaveThresholdMs = 7_200_000 }) {
    this.#location = location
    this.#onEnter = onEnter
    this.#onLeave = onLeave
    this.#enterThresholdMs = enterThresholdMs
    this.#leaveThresholdMs = leaveThresholdMs
  }

  async start() {
    if (isNative()) {
      await this.#startNative()
    } else {
      this.#startWeb()
    }
  }

  stop() {
    if (this.#hysteresisTimer) { clearTimeout(this.#hysteresisTimer); this.#hysteresisTimer = null; this.#pendingInside = null; this.#pendingCrossedAt = null }
    if (this.#nativePlugin) {
      if (this.#nativeWatcherId !== null) {
        this.#nativePlugin.removeWatcher?.({ id: this.#nativeWatcherId })
        this.#nativeWatcherId = null
      }
      this.#nativePlugin = null
    }
    if (this.#watchId !== null && typeof navigator !== 'undefined') {
      navigator.geolocation.clearWatch(this.#watchId)
      this.#watchId = null
    }
  }

  updateLocation(location) {
    this.#location = location
    this.#insideOffice = null
    this.#pendingInside = null
    this.#pendingCrossedAt = null
    if (this.#hysteresisTimer) { clearTimeout(this.#hysteresisTimer); this.#hysteresisTimer = null }
  }

  // ── Native (Capacitor background geolocation) ─────────────────
  async #startNative() {
    try {
      const { BackgroundGeolocation } = await import('@capgo/background-geolocation')
      this.#nativePlugin = BackgroundGeolocation

      this.#nativeWatcherId = await BackgroundGeolocation.addWatcher(
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

    // On first position fix, silently initialize state without firing any callback.
    // We have no knowledge of prior confirmed state, so don't synthesize an onLeave.
    if (this.#insideOffice === null) {
      this.#insideOffice = nowInside
      return
    }

    if (nowInside === this.#insideOffice) {
      // Back to confirmed state — cancel any pending transition (bounce-back)
      if (this.#hysteresisTimer) {
        clearTimeout(this.#hysteresisTimer)
        this.#hysteresisTimer = null
        this.#pendingInside = null
      }
      return
    }

    if (nowInside === this.#pendingInside) {
      // Already waiting to confirm this direction.
      // Also fire immediately if the setTimeout was delayed in background (Doze, throttling).
      const threshold = nowInside ? this.#enterThresholdMs : this.#leaveThresholdMs
      if (Date.now() - this.#pendingCrossedAt.getTime() >= threshold) {
        clearTimeout(this.#hysteresisTimer)
        this.#hysteresisTimer = null
        this.#pendingInside = null
        const crossedAt = this.#pendingCrossedAt
        this.#pendingCrossedAt = null
        this.#insideOffice = nowInside
        if (nowInside) this.#onEnter(crossedAt)
        else           this.#onLeave(crossedAt)
      }
      return
    }

    // New transition direction — record crossing time, start threshold timer
    if (this.#hysteresisTimer) clearTimeout(this.#hysteresisTimer)
    this.#pendingInside = nowInside
    this.#pendingCrossedAt = new Date()
    const threshold = nowInside ? this.#enterThresholdMs : this.#leaveThresholdMs
    this.#hysteresisTimer = setTimeout(() => {
      this.#hysteresisTimer = null
      this.#pendingInside = null
      const crossedAt = this.#pendingCrossedAt
      this.#pendingCrossedAt = null
      this.#insideOffice = nowInside
      if (nowInside) this.#onEnter(crossedAt)
      else           this.#onLeave(crossedAt)
    }, threshold)
  }
}
