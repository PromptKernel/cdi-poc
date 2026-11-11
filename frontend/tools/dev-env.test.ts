import { describe, expect, it } from 'vitest'
import { runtimeConfigFromEnv, serverOptions, webPort } from './dev-env'

describe('webPort / serverOptions', () => {
  it('uses the documented defaults when nothing is set', () => {
    expect(serverOptions({}, 5173)).toEqual({ host: '127.0.0.1', port: 5173, strictPort: true })
    expect(serverOptions({}, 4173).port).toBe(4173)
  })
  it('reads host and port from the environment', () => {
    expect(serverOptions({ CDI_WEB_HOST: '127.0.0.2', CDI_WEB_PORT: '6001' }, 5173)).toEqual({ host: '127.0.0.2', port: 6001, strictPort: true })
  })
  it('rejects a port that is not a port', () => {
    for (const bad of ['abc', '0', '70000', '1.5', '-3']) expect(() => webPort({ CDI_WEB_PORT: bad }, 1)).toThrow(/CDI_WEB_PORT/)
  })
})

describe('runtimeConfigFromEnv', () => {
  it('is null (use the real config.json) when CDI_API_BASE_URL is unset or empty', () => {
    expect(runtimeConfigFromEnv({})).toBeNull()
    expect(runtimeConfigFromEnv({ CDI_API_BASE_URL: '' })).toBeNull()
  })
  it('builds the runtime config from the variable', () => {
    expect(JSON.parse(runtimeConfigFromEnv({ CDI_API_BASE_URL: 'http://127.0.0.1:8123/' })!)).toEqual({ apiBaseUrl: 'http://127.0.0.1:8123' })
  })
  it('refuses anything but an http(s) URL', () => {
    expect(() => runtimeConfigFromEnv({ CDI_API_BASE_URL: 'javascript:1' })).toThrow(/http/)
    expect(() => runtimeConfigFromEnv({ CDI_API_BASE_URL: 'nope' })).toThrow(/not a valid URL/)
  })
})
