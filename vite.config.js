import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  base: '/working-hours-counter/',
  envPrefix: ['VITE_', 'NEXT_PUBLIC_']
})
