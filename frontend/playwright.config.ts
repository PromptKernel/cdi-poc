import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Smoke tests against the BUILT app served by `vite preview`, in three modes:
//   snapshot   static data from e2e/fixtures/explorer (config.json has no apiBaseUrl)
//   live       the real read-only API (`cdi serve`) over the JSON-store baseline e2e/fixtures/live/baseline.json
//   live-auth  the same API started with a bearer token (the page must ask for it)
// Each preview server answers /config.json from its own file (EXPLORER_RUNTIME_CONFIG), so the API URL is runtime configuration, not part of the build.
const here = path.dirname(fileURLToPath(import.meta.url))
const fx = (p: string) => path.join(here, 'e2e/fixtures', p)
const cdi = process.env.CDI_BIN ?? path.join(here, '../.venv/bin/cdi')
const api = (port: number, origin: number, env = '') =>
  `${env}${cdi} serve --config ${path.join(here, '../config.example/config.yml')} --store-path ${fx('live/baseline.json')} --reports-dir ${fx('live')} --port ${port} --cors-origin http://127.0.0.1:${origin}`
const common = { timeout: 120_000, reuseExistingServer: false }

export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: { browserName: 'chromium', headless: true, screenshot: 'off', trace: 'off', video: 'off' },
  projects: [
    { name: 'snapshot', testMatch: /smoke\.spec\.ts/, use: { baseURL: 'http://127.0.0.1:4173' } },
    { name: 'live', testMatch: /smoke\.spec\.ts/, use: { baseURL: 'http://127.0.0.1:4174' } },
    { name: 'live-auth', testMatch: /auth\.spec\.ts/, use: { baseURL: 'http://127.0.0.1:4175' } },
  ],
  webServer: [
    // The first server builds; the others only preview the same dist/.
    { command: 'npm run build && npm run preview', url: 'http://127.0.0.1:4173', ...common, env: { EXPLORER_DATA_DIR: fx('explorer') } },
    { command: api(8765, 4174), url: 'http://127.0.0.1:8765/api/health', ...common },
    { command: 'vite preview --port 4174 --strictPort', url: 'http://127.0.0.1:4174', ...common, env: { EXPLORER_RUNTIME_CONFIG: fx('live/config.live.json'), EXPLORER_DATA_DIR: fx('explorer') } },
    { command: api(8766, 4175), url: 'http://127.0.0.1:8766/api/health', ...common, env: { CDI_API_TOKEN: 'e2e-token-not-a-secret' } },
    { command: 'vite preview --port 4175 --strictPort', url: 'http://127.0.0.1:4175', ...common, env: { EXPLORER_RUNTIME_CONFIG: fx('live/config.auth.json'), EXPLORER_DATA_DIR: fx('explorer') } },
  ],
})
