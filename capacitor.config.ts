import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.taljacob.workinghours',
  appName: 'Working Hours',
  webDir: 'dist',
  server: {
    androidScheme: 'https'
  }
}

export default config
