import { useCallback, useMemo, useState } from 'react'
import type { Index } from '../lib/graph'
import { CONFIDENCES, type Confidence } from '../lib/graph'
import { allConfidences, defaultFilters, directionLabel, distinctValues, expand, search, visibleEdges, visibleNodes, type Direction, type Filters } from '../lib/filters'
import type { LinkConfig } from '../lib/github'
import GraphView from './GraphView'
import SidePanel from './SidePanel'
import Legend from './Legend'

export type Selection = { type: 'node' | 'edge'; id: string } | null

export default function GraphPage({ ix, linkCfg }: { ix: Index; linkCfg: LinkConfig | null }) {
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<Filters>(defaultFilters())
  const [direction, setDirection] = useState<Direction>('upstream')
  const [depth, setDepth] = useState(1)
  const [shown, setShown] = useState<Set<string>>(new Set())
  const [selection, setSelection] = useState<Selection>(null)
  const [note, setNote] = useState('')

  const repos = useMemo(() => distinctValues(ix, 'repo'), [ix])
  const kinds = useMemo(() => distinctValues(ix, 'kind'), [ix])
  const results = useMemo(() => search(ix, query, filters, 12), [ix, query, filters])
  const nodes = useMemo(() => visibleNodes(ix, shown, filters), [ix, shown, filters])
  const edges = useMemo(() => visibleEdges(ix, new Set(nodes.map((n) => n.id)), filters), [ix, nodes, filters])

  const doExpand = useCallback((id: string) => {
    const r = expand(ix, [id], direction, depth, filters)
    setShown((s) => new Set([...s, ...r.nodes]))
    setNote(`${directionLabel(direction)} · depth ${depth} · +${r.nodes.size - 1} node(s)${r.truncated ? ' · stopped at the depth limit (more beyond)' : ''}`)
  }, [ix, direction, depth, filters])

  const pick = (id: string) => { setShown((s) => new Set([...s, id])); setSelection({ type: 'node', id }); setQuery('') }
  const toggle = <T,>(set: Set<T> | null, all: T[], v: T): Set<T> | null => {
    const cur = new Set(set ?? all); cur.has(v) ? cur.delete(v) : cur.add(v)
    return cur.size === all.length ? null : cur
  }

  return (
    <div className="graphpage">
      <aside className="left" aria-label="Controls">
        <section>
          <label htmlFor="search">Search by name</label>
          <input id="search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search nodes by name" autoComplete="off" />
          {results.length > 0 && (
            <ul className="results" role="listbox" aria-label="Search results">
              {results.map((n) => (
                <li key={n.id}>
                  <button role="option" onClick={() => pick(n.id)} title={n.id}>
                    <b>{n.name}</b> <span className="dim">{n.kind} · {n.repo}{n.synthetic ? ' · synthetic' : ''}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h2>Expand</h2>
          <fieldset>
            <legend>Direction</legend>
            {(['upstream', 'downstream'] as Direction[]).map((d) => (
              <label key={d} className="radio"><input type="radio" name="dir" checked={direction === d} onChange={() => setDirection(d)} />{directionLabel(d)}</label>
            ))}
          </fieldset>
          <label htmlFor="depth">Depth: {depth}</label>
          <input id="depth" type="range" min={1} max={12} value={depth} onChange={(e) => setDepth(+e.target.value)} />
          <div className="row">
            <button disabled={selection?.type !== 'node'} onClick={() => selection?.type === 'node' && doExpand(selection.id)}>Expand selected</button>
            <button onClick={() => { setShown(new Set()); setSelection(null); setNote('') }}>Clear</button>
          </div>
          <p className="hint">Click a node in the graph to select it and expand its neighbours.</p>
          {note && <p className="note" aria-live="polite">{note}</p>}
        </section>
        <section>
          <h2>Filters</h2>
          <details open><summary>Repo</summary>
            {repos.map((r) => <label key={r} className="check"><input type="checkbox" checked={!filters.repos || filters.repos.has(r)} onChange={() => setFilters({ ...filters, repos: toggle(filters.repos, repos, r) })} />{r}</label>)}
          </details>
          <details><summary>Node kind</summary>
            {kinds.map((k) => <label key={k} className="check"><input type="checkbox" checked={!filters.kinds || filters.kinds.has(k)} onChange={() => setFilters({ ...filters, kinds: toggle(filters.kinds, kinds, k) })} />{k}</label>)}
          </details>
          <details open><summary>Confidence</summary>
            {CONFIDENCES.map((c) => (
              <label key={c} className="check"><input type="checkbox" checked={filters.confidences.has(c)} onChange={() => {
                const s = new Set<Confidence>(filters.confidences); s.has(c) ? s.delete(c) : s.add(c); setFilters({ ...filters, confidences: s.size ? s : allConfidences() })
              }} />{c}</label>
            ))}
            <label className="check"><input type="checkbox" checked={!filters.hideTypes.has('USES_TYPE')} onChange={(e) => setFilters({ ...filters, hideTypes: new Set(e.target.checked ? [] : ['USES_TYPE']) })} />show type references (USES_TYPE)</label>
          </details>
        </section>
        <Legend />
      </aside>
      <main className="center">
        <GraphView ix={ix} nodes={nodes} edges={edges} selection={selection} onSelect={(s) => { setSelection(s); if (s?.type === 'node') doExpand(s.id) }} />
        <details className="visible" open>
          <summary>Visible nodes ({nodes.length}) and edges ({edges.length})</summary>
          <ul data-testid="visible-nodes">
            {nodes.map((n) => <li key={n.id}><button onClick={() => setSelection({ type: 'node', id: n.id })}>{n.name}</button> <span className="dim">{n.kind}</span></li>)}
          </ul>
        </details>
      </main>
      <aside className="right" aria-label="Details"><SidePanel ix={ix} selection={selection} linkCfg={linkCfg} onSelect={setSelection} /></aside>
    </div>
  )
}
