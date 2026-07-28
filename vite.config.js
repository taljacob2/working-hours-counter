import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { writeFileSync, readFileSync, unlinkSync, existsSync } from 'fs'
import { exec } from 'child_process'

export default defineConfig({
  plugins: [
    svelte(),
    {
      name: 'xls-merger-api',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          // Normalize url in case it contains query params or base prefix
          const url = req.url ? req.url.split('?')[0] : ''
          const isMergeRoute = url === '/api/merge-xls' || url === '/working-hours-counter/api/merge-xls'
          
          if (isMergeRoute && req.method === 'POST') {
            let body = ''
            req.on('data', chunk => { body += chunk })
            req.on('end', () => {
              try {
                const { xlsBase64, logs, colorHomeHours } = JSON.parse(body)
                if (!xlsBase64 || !logs) {
                  res.statusCode = 400
                  res.setHeader('Content-Type', 'application/json')
                  res.end(JSON.stringify({ error: 'Missing xlsBase64 or logs' }))
                  return
                }
                const colorHomeHoursArg = colorHomeHours === true ? 'true' : 'false'

                const id = Math.random().toString(36).substring(7)
                const tempIn = `_temp_in_${id}.xls`
                const tempLogs = `_temp_logs_${id}.json`
                const tempOut = `_temp_out_${id}.xls`

                writeFileSync(tempIn, Buffer.from(xlsBase64, 'base64'))
                writeFileSync(tempLogs, JSON.stringify(logs))

                exec(`python merge_hours.py "${tempIn}" "${tempLogs}" "${tempOut}" ${colorHomeHoursArg}`, (error, stdout, stderr) => {
                  const cleanup = () => {
                    try { if (existsSync(tempIn)) unlinkSync(tempIn) } catch(e){}
                    try { if (existsSync(tempLogs)) unlinkSync(tempLogs) } catch(e){}
                    try { if (existsSync(tempOut)) unlinkSync(tempOut) } catch(e){}
                  }

                  if (error) {
                    cleanup()
                    res.statusCode = 500
                    res.setHeader('Content-Type', 'application/json')
                    res.end(JSON.stringify({ error: `Python script error: ${stderr || error.message}` }))
                    return
                  }

                  try {
                    const outBuffer = readFileSync(tempOut)
                    cleanup()
                    res.statusCode = 200
                    res.setHeader('Content-Type', 'application/vnd.ms-excel')
                    res.setHeader('Content-Disposition', 'attachment; filename="merged.xls"')
                    res.end(outBuffer)
                  } catch (readErr) {
                    cleanup()
                    res.statusCode = 500
                    res.setHeader('Content-Type', 'application/json')
                    res.end(JSON.stringify({ error: `Failed to read merged file: ${readErr.message}` }))
                  }
                })
              } catch (parseErr) {
                res.statusCode = 400
                res.setHeader('Content-Type', 'application/json')
                res.end(JSON.stringify({ error: `Invalid JSON payload: ${parseErr.message}` }))
              }
            })
            return
          }
          next()
        })
      }
    }
  ],
  base: process.env.CAPACITOR_BUILD ? '/' : '/working-hours-counter/',
  envPrefix: ['VITE_', 'NEXT_PUBLIC_']
})

