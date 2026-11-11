import { describe, expect, it } from 'vitest'
import { buildIndex, type GEdge, type GNode, type GraphData } from './graph'
import { defaultFilters, directionLabel, edgePasses, expand, nodePasses, search, step, visibleEdges, type Filters } from './filters'
import { githubLink } from './github'

const n = (id: string, kind: string, repo: string, name = id): GNode => ({ id, kind, name, repo, file: `${id}.x`, line: 1, end_line: 2, synthetic: false, attrs: {} })
const e = (s: string, t: string, confidence: GEdge['confidence'] = 'CONFIRMED_STATIC', type = 'CALLS'): GEdge => ({
  id: `${type}|${s}|${t}`, type, source: s, target: t, confidence, source_file: `${s}.x`, line: 3, column: 1, commit_id: 'a'.repeat(40), repo: 'web', synthetic: false,
  reason: confidence === 'CONFIRMED_STATIC' ? null : 'because', evidence: 'x()', analysis_method: 'test:m', attrs: {},
})
// UI -> SVC -> API -> DAL -> PROC -> TABLE ; API -?-> UNRES (unresolved) ; UI2 -> SVC
const data: GraphData = {
  meta: { generated_at: '', source: 'files', notice: '', counts: { nodes: 0, edges: 0 }, baseline: null, repos: { web: { path: 'apps/web', kind: 'frontend' }, api: { path: 'apps/api', kind: 'api' }, db: { path: 'apps/db', kind: 'sql' } } },
  nodes: [n('UI', 'UI_COMPONENT', 'web', 'FetchItemComponent'), n('UI2', 'UI_COMPONENT', 'web', 'Other'), n('SVC', 'UI_SERVICE_METHOD', 'web', 'ItemService.getItems'),
          n('API', 'API_ENDPOINT', 'api', 'ItemController.Index()'), n('DAL', 'DATA_ACCESS_METHOD', 'api'), n('PROC', 'SQL_PROC', 'db', 'dbo.spGetAllItems'),
          n('TBL', 'SQL_TABLE', 'db', 'dbo.tblItem'), n('UNRES', 'UNRESOLVED', 'api', 'dynamic SQL at x:1')],
  edges: [e('UI', 'SVC'), e('UI2', 'SVC'), e('SVC', 'API', 'CONFIRMED_STATIC', 'ROUTES_TO'), e('API', 'DAL', 'INFERRED', 'DISPATCHES_TO'), e('DAL', 'PROC'), e('PROC', 'TBL', 'CONFIRMED_STATIC', 'READS_TABLE'),
          e('DAL', 'UNRES', 'UNRESOLVED', 'EXECUTES_DYNAMIC_SQL'), e('UI', 'TBL', 'CONFIRMED_STATIC', 'USES_TYPE')],
}
const ix = buildIndex(data)
const F = (over: Partial<Filters> = {}): Filters => ({ ...defaultFilters(), ...over })
const ids = (s: Set<string>) => [...s].sort()

describe('direction (matches docs/schema.md)', () => {
  it('upstream = dependencies = follow edges forward', () => {
    expect(step(ix, 'SVC', 'upstream', F()).map((s) => s.other)).toEqual(['API'])
    expect(ids(expand(ix, ['UI'], 'upstream', 10, F()).nodes)).toEqual(['API', 'DAL', 'PROC', 'SVC', 'TBL', 'UI', 'UNRES'])
  })
  it('downstream = consumers = follow edges in reverse', () => {
    expect(step(ix, 'SVC', 'downstream', F()).map((s) => s.other).sort()).toEqual(['UI', 'UI2'])
    expect(ids(expand(ix, ['TBL'], 'downstream', 10, F()).nodes)).toEqual(['API', 'DAL', 'PROC', 'SVC', 'TBL', 'UI', 'UI2'])
  })
  it('the two directions are inverses: if X reaches Y upstream then Y reaches X downstream', () => {
    const up = expand(ix, ['UI'], 'upstream', 10, F()).nodes
    for (const y of up) expect(expand(ix, [y], 'downstream', 10, F()).nodes.has('UI')).toBe(true)
  })
  it('labels name both words so the toggle is unambiguous', () => {
    expect(directionLabel('downstream')).toBe('Downstream: affected by this (consumers)')
    expect(directionLabel('upstream')).toBe('Upstream: depends on (dependencies)')
  })
})

describe('depth', () => {
  it('stops at the depth limit and says so', () => {
    const r1 = expand(ix, ['UI'], 'upstream', 1, F())
    expect(ids(r1.nodes)).toEqual(['SVC', 'UI'])
    expect(r1.truncated).toBe(true)
    expect(ids(expand(ix, ['UI'], 'upstream', 2, F()).nodes)).toEqual(['API', 'SVC', 'UI'])
    expect(expand(ix, ['UI'], 'upstream', 10, F()).truncated).toBe(false)
  })
  it('depth 0 expands nothing', () => expect(ids(expand(ix, ['UI'], 'upstream', 0, F()).nodes)).toEqual(['UI']))
})

describe('filters', () => {
  it('repo filter excludes nodes of other repos from traversal', () => {
    const r = expand(ix, ['UI'], 'upstream', 10, F({ repos: new Set(['web']) }))
    expect(ids(r.nodes)).toEqual(['SVC', 'UI'])
  })
  it('kind filter', () => expect(nodePasses(ix.nodes.get('PROC')!, F({ kinds: new Set(['SQL_TABLE']) }))).toBe(false))
  it('confidence filter: dropping INFERRED cuts the path at the inferred hop; UNRESOLVED edges can be hidden', () => {
    const noInf = new Set<GEdge['confidence']>(['CONFIRMED_STATIC', 'UNRESOLVED'])
    expect(ids(expand(ix, ['UI'], 'upstream', 10, F({ confidences: noInf })).nodes)).toEqual(['API', 'SVC', 'UI'])
    const noUnres = new Set<GEdge['confidence']>(['CONFIRMED_STATIC', 'INFERRED'])
    expect(ids(expand(ix, ['UI'], 'upstream', 10, F({ confidences: noUnres })).nodes)).not.toContain('UNRES')
    expect(edgePasses(ix.edges.get('DISPATCHES_TO|API|DAL')!, F({ confidences: noInf }))).toBe(false)
  })
  it('unresolved edges lead to the placeholder node (a visible dead end) by default', () => {
    const r = expand(ix, ['DAL'], 'upstream', 1, F())
    expect(r.nodes.has('UNRES')).toBe(true)
    expect(ix.edges.get('EXECUTES_DYNAMIC_SQL|DAL|UNRES')!.reason).toBeTruthy()
  })
  it('USES_TYPE edges are hidden by default and can be shown', () => {
    expect(ids(expand(ix, ['UI'], 'upstream', 1, F()).nodes)).toEqual(['SVC', 'UI'])
    expect(ids(expand(ix, ['UI'], 'upstream', 1, F({ hideTypes: new Set() })).nodes)).toEqual(['SVC', 'TBL', 'UI'])
  })
  it('visibleEdges returns edges between visible nodes only, filtered', () => {
    const vis = new Set(['UI', 'SVC', 'API'])
    expect(visibleEdges(ix, vis, F()).map((x) => x.id).sort()).toEqual(['CALLS|UI|SVC', 'ROUTES_TO|SVC|API'])
  })
})

describe('search', () => {
  it('finds by name case-insensitively and ranks exact > prefix > last segment > substring', () => {
    expect(search(ix, 'fetchitemcomponent', F())[0].id).toBe('UI')
    expect(search(ix, 'dbo.tbl', F()).map((x) => x.id)).toEqual(['TBL'])
    expect(search(ix, 'getItems', F())[0].id).toBe('SVC')
    expect(search(ix, 'item', F()).length).toBeGreaterThan(2)
  })
  it('respects node filters and limits, and returns nothing for an empty query', () => {
    expect(search(ix, 'dbo', F({ kinds: new Set(['SQL_TABLE']) })).map((x) => x.id)).toEqual(['TBL'])
    expect(search(ix, '', F())).toEqual([])
    expect(search(ix, 'e', F(), 3).length).toBeLessThanOrEqual(3)
  })
})

describe('github link', () => {
  const cfg = { githubBaseUrl: 'https://example.invalid/org/repo/', linkTemplate: '{base}/blob/{commit}/{repoPath}/{file}#L{line}' }
  const sha = 'a'.repeat(40)
  it('builds a blob URL from base URL, the edge commit, the repo folder, file and line', () => {
    expect(githubLink(cfg, data.meta, 'api', 'Controllers/ItemController.cs', 27, sha)).toBe(`https://example.invalid/org/repo/blob/${sha}/apps/api/Controllers/ItemController.cs#L27`)
  })
  it('encodes path segments', () => expect(githubLink(cfg, data.meta, 'web', 'src/a b/c#.ts', 1, sha)).toContain('src/a%20b/c%23.ts#L1'))
  it('returns null when the commit, file, repo folder or config is missing or malformed', () => {
    expect(githubLink(cfg, data.meta, 'api', null, 1, sha)).toBeNull()
    expect(githubLink(cfg, data.meta, 'api', 'f.cs', 1, null)).toBeNull()
    expect(githubLink(cfg, data.meta, 'api', 'f.cs', 1, 'not-a-sha')).toBeNull()
    expect(githubLink(cfg, data.meta, 'nope', 'f.cs', 1, sha)).toBeNull()
    expect(githubLink(null, data.meta, 'api', 'f.cs', 1, sha)).toBeNull()
  })
})
