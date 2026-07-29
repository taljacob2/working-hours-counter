import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  base: process.env.CAPACITOR_BUILD ? '/' : '/working-hours-counter/',
  envPrefix: ['VITE_', 'NEXT_PUBLIC_'],
  server: {
    // Without this, Vite's file watcher also watches the native Android project.
    // A Gradle build touches tens of thousands of files under android/app/build
    // in a couple of minutes, and the resulting flood of watch events has been
    // observed to blow up the dev server's memory (6GB+ within 5 minutes).
    watch: {
      ignored: ['**/android/**', '**/ios/**']
    }
  }
})
