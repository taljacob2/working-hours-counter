// OAuth sign-in providers, gated off until their app is registered (Google
// Cloud Console / GitHub OAuth Apps) and enabled under Supabase
// Authentication > Providers. Flip a provider to `true` once both sides are
// configured.
export const OAUTH_PROVIDERS = {
  google: true,
  github: true,
}

export const hasEnabledOAuthProvider = Object.values(OAUTH_PROVIDERS).some(Boolean)
