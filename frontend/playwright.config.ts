import { defineConfig } from '@playwright/test'

// Smoke test against the BUILT app served by `vite preview`; data comes from e2e/fixtures/explorer via the preview middleware.
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:4173', browserName: 'chromium', headless: true, screenshot: 'off', trace: 'off', video: 'off' },
  webServer: { command: 'npm run build && npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: false, timeout: 120_000,
    env: { EXPLORER_DATA_DIR: new URL('./e2e/fixtures/explorer', import.meta.url).pathname } },
})
