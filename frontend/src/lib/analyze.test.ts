import { describe, expect, it } from 'vitest'
import { describeBaseline } from './analyze'
import type { GraphMeta } from './graph'

const meta = (baseline: GraphMeta['baseline']): GraphMeta => ({
  generated_at: '', source: 'live-api', notice: '', counts: { nodes: 3, edges: 2 }, baseline,
  repos: { web: { path: 'apps/web', kind: 'frontend' }, db: { path: 'apps/db', kind: 'sql' }, api: { path: 'apps/api', kind: 'api' } },
})

describe('describeBaseline', () => {
  it('lists every repo with its full commit id, plus load time and schema version', () => {
    const f = describeBaseline(meta({ commits: { web: 'a'.repeat(40), api: 'b'.repeat(40), db: 'c'.repeat(40) }, loaded_at: '2026-01-01T00:00:00+00:00', mode: 'full', schema_version: 1 }))
    expect(f.rows.map((r) => r.repo)).toEqual(['api', 'db', 'web'])
    expect(f.rows[0]).toEqual({ repo: 'api', kind: 'api', path: 'apps/api', commit: 'b'.repeat(40), short: 'bbbbbbbb' })
    expect(f).toMatchObject({ schemaVersion: '1', mode: 'full', loadedAt: '2026-01-01T00:00:00+00:00', counts: '3 nodes, 2 edges' })
  })
  it('says "not recorded" instead of inventing facts (older snapshots, repos without a commit)', () => {
    const f = describeBaseline(meta({ commits: { web: 'a'.repeat(40) }, loaded_at: null, mode: null }))
    expect(f).toMatchObject({ schemaVersion: 'not recorded', mode: 'not recorded', loadedAt: 'not recorded' })
    expect(f.rows.find((r) => r.repo === 'db')).toMatchObject({ commit: null, short: 'not recorded' })
    expect(describeBaseline(meta(null)).rows.every((r) => r.commit === null)).toBe(true)
  })
  it('keeps a commit for a repo that is no longer in the configuration', () => {
    const f = describeBaseline(meta({ commits: { gone: 'd'.repeat(40) }, loaded_at: null, mode: null }))
    expect(f.rows.find((r) => r.repo === 'gone')).toMatchObject({ commit: 'd'.repeat(40), kind: '?' })
  })
})
