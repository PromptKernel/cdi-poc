import { describe, expect, it } from 'vitest'
import { loadRuntime, parseRuntime } from './runtime'

const resp = (status: number, body?: unknown, raw?: string) => new Response(raw ?? (body === undefined ? null : JSON.stringify(body)), { status })

describe('parseRuntime', () => {
  it('null, missing and empty apiBaseUrl mean snapshot mode', () => {
    for (const v of [{}, { apiBaseUrl: null }, { apiBaseUrl: '' }]) expect(parseRuntime(v)).toEqual({ apiBaseUrl: null })
  })
  it('accepts http(s) URLs and strips trailing slashes', () => {
    expect(parseRuntime({ apiBaseUrl: 'http://127.0.0.1:8000/' }).apiBaseUrl).toBe('http://127.0.0.1:8000')
    expect(parseRuntime({ apiBaseUrl: 'https://api.example.invalid//' }).apiBaseUrl).toBe('https://api.example.invalid')
  })
  it('rejects everything else with a message that names the file', () => {
    expect(() => parseRuntime({ apiBaseUrl: 'javascript:alert(1)' })).toThrow(/http:\/\/ or https:\/\//)
    expect(() => parseRuntime({ apiBaseUrl: 'not a url' })).toThrow(/not a valid URL/)
    expect(() => parseRuntime({ apiBaseUrl: 5 })).toThrow(/string or null/)
    expect(() => parseRuntime([])).toThrow(/JSON object/)
    expect(() => parseRuntime(null)).toThrow(/JSON object/)
  })
})

describe('loadRuntime', () => {
  it('reads config.json at run time (the URL comes from the file, not from the build)', async () => {
    const seen: string[] = []
    const f = (async (u: string) => { seen.push(u); return resp(200, { apiBaseUrl: 'http://127.0.0.1:9' }) }) as unknown as typeof fetch
    expect(await loadRuntime(f)).toEqual({ apiBaseUrl: 'http://127.0.0.1:9' })
    expect(seen).toEqual(['config.json'])
  })
  it('a missing file or an unreachable server means snapshot mode', async () => {
    expect(await loadRuntime((async () => resp(404)) as unknown as typeof fetch)).toEqual({ apiBaseUrl: null })
    expect(await loadRuntime((async () => { throw new TypeError('network') }) as unknown as typeof fetch)).toEqual({ apiBaseUrl: null })
  })
  it('a file that exists but is broken is an error, not a silent fallback', async () => {
    await expect(loadRuntime((async () => resp(200, undefined, '{oops')) as unknown as typeof fetch)).rejects.toThrow(/not valid JSON/)
    await expect(loadRuntime((async () => resp(500)) as unknown as typeof fetch)).rejects.toThrow(/\(500\)/)
    await expect(loadRuntime((async () => resp(200, { apiBaseUrl: 'ftp://x' })) as unknown as typeof fetch)).rejects.toThrow(/http/)
  })
})
