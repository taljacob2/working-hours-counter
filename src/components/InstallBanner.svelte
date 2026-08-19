<script>
  import { canInstall, promptInstall, isIOS, isStandalone } from '../lib/installPrompt.js'

  const DISMISS_KEY = 'whl_install_dismissed_at'
  const COOLDOWN_DAYS = 30

  function isDismissed() {
    const raw = localStorage.getItem(DISMISS_KEY)
    if (!raw) return false
    return (Date.now() - Number(raw)) / 86_400_000 < COOLDOWN_DAYS
  }

  let dismissed = isDismissed()
  const isNative = !!window.Capacitor?.isNativePlatform?.()
  const iOS = isIOS()
  const standalone = isStandalone()

  $: hidden = dismissed || isNative || standalone
  $: showAndroidPrompt = !hidden && $canInstall
  $: showIOSInstructions = !hidden && iOS && !$canInstall

  function dismiss() {
    dismissed = true
    localStorage.setItem(DISMISS_KEY, String(Date.now()))
  }

  async function install() {
    if (await promptInstall()) dismiss()
  }
</script>

{#if showAndroidPrompt}
  <div class="install-banner" role="complementary">
    <button class="install-banner__dismiss" aria-label="Dismiss" on:click={dismiss}>✕</button>
    <span class="install-banner__icon">📲</span>
    <div class="install-banner__body">
      <strong>Install Work Hours Logger</strong>
      <span>Add it to your home screen for quick, full-screen access.</span>
      <button class="btn btn-primary btn-sm install-banner__install" on:click={install}>Install</button>
    </div>
  </div>
{:else if showIOSInstructions}
  <div class="install-banner" role="complementary">
    <button class="install-banner__dismiss" aria-label="Dismiss" on:click={dismiss}>✕</button>
    <span class="install-banner__icon">📲</span>
    <div class="install-banner__body">
      <strong>Install Work Hours Logger</strong>
      <span>
        Tap <strong>Share</strong>
        <svg class="install-banner__share-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 15V4" />
          <path d="M8 8l4-4 4 4" />
          <path d="M5 12v7a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7" />
        </svg>
        , then <strong>Add to Home Screen</strong>.
      </span>
    </div>
  </div>
{/if}

<style>
  .install-banner {
    position: fixed;
    bottom: 1.5rem;
    left: 0;
    right: 0;
    margin: 0 auto;
    width: fit-content;
    z-index: 9998;
    display: flex;
    align-items: flex-start;
    gap: 0.625rem;
    padding: 0.75rem 0.875rem;
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-md);
    background: var(--color-surface);
    border: 1.5px solid var(--color-border);
    color: var(--color-text);
    max-width: 340px;
    padding-right: 1.75rem;
    animation: slideIn 0.2s ease;
  }
  .install-banner__icon { font-size: 1.25rem; line-height: 1; }
  .install-banner__body {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.375rem;
    font-size: 0.8125rem;
    color: var(--color-text-muted);
    flex: 1;
  }
  .install-banner__body strong { color: var(--color-text); font-size: 0.875rem; }
  .install-banner__install { margin-top: 0.125rem; }
  .install-banner__share-icon {
    width: 13px;
    height: 13px;
    vertical-align: -1px;
    margin: 0 1px;
  }
  .install-banner__dismiss {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    font-size: 0.8rem;
    line-height: 1;
    padding: 0.25rem;
  }
  .install-banner__dismiss:hover { color: var(--color-text); }
  @keyframes slideIn {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @media (max-width: 600px) {
    .install-banner {
      left: 0.75rem;
      right: 0.75rem;
      width: auto;
      max-width: none;
      bottom: calc(4.5rem + env(safe-area-inset-bottom) + 0.75rem);
    }
  }
</style>
