import { defineConfig } from '@playwright/test'

// Smoke test against the BUILT app served by `vite preview` (data comes from ../out/explorer via the preview middleware).
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  globalSetup: './e2e/global-setup.ts',
  use: { baseURL: 'http://127.0.0.1:4173', browserName: 'chromium', headless: true, screenshot: 'off', trace: 'off', video: 'off' },
  webServer: { command: 'npm run build && npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: !process.env.CI, timeout: 120_000 },
})
