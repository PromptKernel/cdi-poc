// Environment-driven settings for the dev and preview servers. Nothing here is a build-time constant of the app itself:
//   CDI_WEB_HOST      listen address (default 127.0.0.1)
//   CDI_WEB_PORT      listen port (default 5173 for `npm run dev`, 4173 for `npm run preview`)
//   CDI_API_BASE_URL  when set, the server answers /config.json with {"apiBaseUrl": <that URL>} so the page talks to the live API.
//                     (A deployed folder just edits its own config.json.) The API must allow this page's origin: `cdi serve --cors-origin` / $CDI_CORS_ORIGINS.
type Env = Record<string, string | undefined>

export function webPort(env: Env, fallback: number): number {
  const raw = env.CDI_WEB_PORT
  if (raw === undefined || raw === '') return fallback
  const n = Number(raw)
  if (!Number.isInteger(n) || n < 1 || n > 65535) throw new Error(`CDI_WEB_PORT must be a port number (1-65535), got ${JSON.stringify(raw)}`)
  return n
}

export function serverOptions(env: Env, fallbackPort: number) {
  return { host: env.CDI_WEB_HOST || '127.0.0.1', port: webPort(env, fallbackPort), strictPort: true }
}

/** JSON text for /config.json derived from CDI_API_BASE_URL, or null when the variable is not set. Only http(s) URLs are accepted. */
export function runtimeConfigFromEnv(env: Env): string | null {
  const raw = env.CDI_API_BASE_URL
  if (raw === undefined || raw === '') return null
  let u: URL
  try { u = new URL(raw) } catch { throw new Error(`CDI_API_BASE_URL is not a valid URL: ${raw}`) }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error('CDI_API_BASE_URL must start with http:// or https://')
  return JSON.stringify({ apiBaseUrl: raw.replace(/\/+$/, '') })
}
