export interface Runtime { apiBaseUrl: string | null }

/** Thrown when the API answers 401: the page asks for a token. */
export class AuthError extends Error {}

/** Validate config.json. apiBaseUrl must be null/absent (snapshot mode) or an http(s) URL; anything else is a configuration error shown to the user. */
export function parseRuntime(raw: unknown): Runtime {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('config.json must be a JSON object')
  const v = (raw as Record<string, unknown>).apiBaseUrl
  if (v === undefined || v === null || v === '') return { apiBaseUrl: null }
  if (typeof v !== 'string') throw new Error('config.json: apiBaseUrl must be a string or null')
  let u: URL
  try { u = new URL(v) } catch { throw new Error(`config.json: apiBaseUrl is not a valid URL: ${v}`) }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error('config.json: apiBaseUrl must start with http:// or https://')
  return { apiBaseUrl: v.replace(/\/+$/, '') }
}

/** Read config.json at runtime. A missing file means snapshot mode; a file that exists but is invalid is an error (never silently ignored). */
export async function loadRuntime(fetchFn: typeof fetch = fetch, url = 'config.json'): Promise<Runtime> {
  let r: Response
  try { r = await fetchFn(url, { cache: 'no-store' }) } catch { return { apiBaseUrl: null } }
  if (r.status === 404) return { apiBaseUrl: null }
  if (!r.ok) throw new Error(`could not read ${url} (${r.status})`)
  let doc: unknown
  try { doc = await r.json() } catch { throw new Error(`${url} is not valid JSON`) }
  return parseRuntime(doc)
}

const KEY = 'cdi.apiToken'
export const getToken = (): string | null => { try { return sessionStorage.getItem(KEY) } catch { return null } }
export const setToken = (t: string) => { try { sessionStorage.setItem(KEY, t) } catch { /* storage unavailable: the token lasts until reload */ } }
export const clearToken = () => { try { sessionStorage.removeItem(KEY) } catch { /* ignore */ } }
