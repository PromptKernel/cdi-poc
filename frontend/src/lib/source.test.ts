import { describe, expect, it } from 'vitest'
import { AuthError } from './runtime'
import { joinUrl, makeSource } from './source'

type Call = { url: string; auth: string | null }
function fake(routes: Record<string, () => Response>) {
  const calls: Call[] = []
  const f = (async (url: string, init?: RequestInit) => {
    calls.push({ url, auth: ((init?.headers ?? {}) as Record<string, string>).Authorization ?? null })
    const r = routes[url]
    if (!r) return new Response('{"detail":"nope"}', { status: 404 })
    return r()
  }) as unknown as typeof fetch
  return { f, calls }
}
const json = (o: unknown, status = 200) => () => new Response(JSON.stringify(o), { status })

describe('joinUrl', () => {
  it('joins without doubled or missing slashes', () => {
    expect(joinUrl('http://h:1', '/api/x')).toBe('http://h:1/api/x')
    expect(joinUrl('http://h:1/', 'api/x')).toBe('http://h:1/api/x')
  })
})

describe('live source', () => {
  const rt = { apiBaseUrl: 'http://127.0.0.1:8000' }
  it('says it is the live API and reads graph, reports and PR files from /api', async () => {
    const { f, calls } = fake({
      'http://127.0.0.1:8000/api/graph': json({ meta: {}, nodes: [], edges: [] }),
      'http://127.0.0.1:8000/api/reports': json({ reports: [{ name: 'a', md: '/api/reports/a?format=md', json: null, modified: 't' }] }),
      'http://127.0.0.1:8000/api/reports/a?format=md': () => new Response('# a'),
      'http://127.0.0.1:8000/api/pr': json({ comment: 'c', status: { s: 1 } }),
    })
    const s = makeSource(rt, f)
    expect(s.kind).toBe('live')
    expect(s.label).toContain('live API')
    expect((await s.loadGraph()).nodes).toEqual([])
    const list = await s.reportsIndex()
    expect(await s.text(list[0].md)).toBe('# a')
    expect(await s.pr()).toEqual({ comment: 'c', status: { s: 1 } })
    expect(calls.every((c) => c.url.startsWith('http://127.0.0.1:8000/api/'))).toBe(true)
  })
  it('sends the bearer token only when there is one', async () => {
    const { f, calls } = fake({ 'http://127.0.0.1:8000/api/graph': json({}) })
    await makeSource(rt, f, () => null).loadGraph()
    await makeSource(rt, f, () => 'abc').loadGraph()
    expect(calls.map((c) => c.auth)).toEqual([null, 'Bearer abc'])
  })
  it('a 401 becomes an AuthError so the page can ask for a token', async () => {
    const { f } = fake({ 'http://127.0.0.1:8000/api/graph': json({ detail: 'x' }, 401) })
    await expect(makeSource(rt, f).loadGraph()).rejects.toBeInstanceOf(AuthError)
  })
  it('API errors show the server\'s detail; an unreachable API names the URL and the CORS hint', async () => {
    const { f } = fake({ 'http://127.0.0.1:8000/api/graph': json({ detail: 'no baseline available: x' }, 503) })
    await expect(makeSource(rt, f).loadGraph()).rejects.toThrow(/API 503: no baseline available/)
    const down = (async () => { throw new TypeError('Failed to fetch') }) as unknown as typeof fetch
    await expect(makeSource(rt, down).loadGraph()).rejects.toThrow(/cannot reach the API at http:\/\/127.0.0.1:8000.*cors-origin/)
  })
  it('never sends the token to snapshot files', async () => {
    const { f, calls } = fake({ 'data/graph.json': json({}) })
    await makeSource({ apiBaseUrl: null }, f, () => 'secret').loadGraph()
    expect(calls[0].auth).toBeNull()
  })
})

describe('snapshot source', () => {
  it('reads the files written by cdi export', async () => {
    const { f } = fake({
      'data/graph.json': json({ nodes: [1] }), 'data/reports/index.json': json({ reports: [{ name: 'x', md: 'reports/report-x.md', json: null, modified: 't' }] }),
      'data/reports/report-x.md': () => new Response('# x'), 'data/pr/index.json': json({ comment: 'pr/pr-comment.md', status: null }), 'data/pr/pr-comment.md': () => new Response('hi'),
    })
    const s = makeSource({ apiBaseUrl: null }, f)
    expect(s.kind).toBe('snapshot')
    expect(s.label).toContain('snapshot')
    expect(((await s.loadGraph()) as unknown as { nodes: number[] }).nodes).toEqual([1])
    const list = await s.reportsIndex()
    expect(await s.text(list[0].md)).toBe('# x')
    expect(await s.pr()).toEqual({ comment: 'hi', status: null })
  })
  it('a missing snapshot says how to create one', async () => {
    await expect(makeSource({ apiBaseUrl: null }, fake({}).f).loadGraph()).rejects.toThrow(/cdi export/)
  })
})
