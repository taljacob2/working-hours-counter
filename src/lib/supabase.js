import { createClient } from '@supabase/supabase-js'

let _client = null

export function initSupabase(url, anonKey) {
  _client = createClient(url, anonKey)
  return _client
}

export function getSupabase() {
  return _client
}
