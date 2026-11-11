import type { GraphData } from './graph'
import { AuthError, type Runtime } from './runtime'

export interface ReportEntry { name: string; md: string; json: string | null; modified: string; summary?: { objects: number; pr: string; labels: string[]; warnings: number } }
export interface PrFiles { comment: string | null; status: unknown | null }

/** Where the explorer's data comes from: the live read-only API, or the static snapshot written by `cdi export`. */
export interface DataSource {
  kind: 'live' | 'snapshot'
  label: string
  loadGraph(): Promise<GraphData>
  reportsIndex(): Promise<ReportEntry[]>
  text(rel: string): Promise<string>
  pr(): Promise<PrFiles>
}

export const joinUrl = (base: string, path: string) => base.replace(/\/+$/, '') + '/' + path.replace(/^\/+/, '')

export function makeSource(rt: Runtime, fetchFn: typeof fetch = fetch, token: () => string | null = () => null): DataSource {
  const live = rt.apiBaseUrl !== null
  const get = async (url: string, what: string): Promise<Response> => {
    const t = live ? token() : null
    let r: Response
    try {
      r = await fetchFn(url, { cache: 'no-store', headers: t ? { Authorization: `Bearer ${t}` } : {} })
    } catch {
      throw new Error(live ? `cannot reach the API at ${rt.apiBaseUrl} (is it running, and is this origin allowed with --cors-origin?)` : `could not load ${what}`)
    }
    if (r.status === 401) throw new AuthError('the API needs a bearer token')
    if (!r.ok) {
      let detail = ''
      try { detail = (await r.json()).detail ?? '' } catch { /* not JSON */ }
      throw new Error(live ? `API ${r.status}: ${detail || r.statusText}` : `could not load ${what} (${r.status}). Run: cdi export`)
    }
    return r
  }
  if (live) {
    const api = (p: string) => joinUrl(rt.apiBaseUrl!, p)
    return {
      kind: 'live', label: `live API (${rt.apiBaseUrl})`,
      loadGraph: async () => (await get(api('/api/graph'), 'graph')).json(),
      reportsIndex: async () => (await (await get(api('/api/reports'), 'reports')).json()).reports,
      text: async (rel) => (await get(api(rel), rel)).text(),
      pr: async () => (await get(api('/api/pr'), 'pr')).json(),
    }
  }
  return {
    kind: 'snapshot', label: 'snapshot (data/)',
    loadGraph: async () => (await get('data/graph.json', 'data/graph.json')).json(),
    reportsIndex: async () => (await (await get('data/reports/index.json', 'reports index')).json()).reports,
    text: async (rel) => (await get(`data/${rel}`, rel)).text(),
    pr: async () => {
      const idx = await (await get('data/pr/index.json', 'PR files')).json()
      return {
        comment: idx.comment ? await (await get(`data/${idx.comment}`, idx.comment)).text() : null,
        status: idx.status ? await (await get(`data/${idx.status}`, idx.status)).json() : null,
      }
    },
  }
}
