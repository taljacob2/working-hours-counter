// Deletes the calling user's own account. Runs with the service_role key
// (needed for auth.admin.deleteUser — no client-side API can remove an
// auth.users row), but only after verifying the caller's own JWT identifies
// a real signed-in user; it always deletes that user and nobody else.
//
// All user_id foreign keys (work_logs, work_settings, push_subscriptions,
// rebalance_history) are ON DELETE CASCADE (see
// supabase-migration-cascade-delete.sql), so removing the auth.users row
// wipes the rest of that user's data automatically — no per-table cleanup
// needed here.
//
// Deploy: .github/workflows/deploy-edge-functions.yml (on push to master).

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  })
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  const authHeader = req.headers.get('Authorization')
  if (!authHeader) return jsonResponse({ error: 'Missing Authorization header' }, 401)

  const supabaseUrl = Deno.env.get('SUPABASE_URL')

  try {
    // Identify the caller from their own JWT — a plain anon-key client can
    // only tell us who's making the request, it can't delete anything.
    const callerClient = createClient(supabaseUrl, Deno.env.get('SUPABASE_ANON_KEY'), {
      global: { headers: { Authorization: authHeader } },
    })
    const { data: { user }, error: userErr } = await callerClient.auth.getUser()
    if (userErr || !user) return jsonResponse({ error: 'Invalid session' }, 401)

    // Only the service_role key can delete an auth.users row.
    const adminClient = createClient(supabaseUrl, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY'))
    const { error: deleteErr } = await adminClient.auth.admin.deleteUser(user.id)
    if (deleteErr) throw deleteErr

    return jsonResponse({ success: true }, 200)
  } catch (err) {
    return jsonResponse({ error: err.message || 'Account deletion failed' }, 500)
  }
})
