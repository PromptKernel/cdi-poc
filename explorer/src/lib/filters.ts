import type { Confidence, GEdge, GNode, Index } from './graph'

/** Direction, matching docs/schema.md. Edges are stored source -> target and mean "source depends on target".
 *  downstream = CONSUMERS: who depends on a node (follow edges in reverse)  -> the impact of changing it
 *  upstream   = DEPENDENCIES: what a node depends on (follow edges forward) -> root-cause tracing */
export type Direction = 'downstream' | 'upstream'

export interface Filters {
  repos: Set<string> | null          // null = every repo
  kinds: Set<string> | null          // null = every kind
  confidences: Set<Confidence>
  hideTypes: Set<string>             // edge types hidden entirely (for example USES_TYPE)
}

export const allConfidences = (): Set<Confidence> => new Set<Confidence>(['CONFIRMED_STATIC', 'INFERRED', 'UNRESOLVED'])
export const defaultFilters = (): Filters => ({ repos: null, kinds: null, confidences: allConfidences(), hideTypes: new Set(['USES_TYPE']) })

export const nodePasses = (n: GNode, f: Filters) => (!f.repos || f.repos.has(n.repo)) && (!f.kinds || f.kinds.has(n.kind))
export const edgePasses = (e: GEdge, f: Filters) => f.confidences.has(e.confidence) && !f.hideTypes.has(e.type)

export interface Step { edge: GEdge; other: string }

/** Neighbours of `id` in the given direction. A neighbour must pass the node filters; the connecting edge must pass the edge filters. */
export function step(ix: Index, id: string, dir: Direction, f: Filters): Step[] {
  const list = dir === 'upstream' ? ix.out.get(id) ?? [] : ix.inn.get(id) ?? []
  const res: Step[] = []
  for (const edge of list) {
    const other = dir === 'upstream' ? edge.target : edge.source
    const n = ix.nodes.get(other)
    if (n && nodePasses(n, f) && edgePasses(edge, f)) res.push({ edge, other })
  }
  return res
}

/** Breadth-first expansion from `starts`, `depth` hops, in one direction. UNRESOLVED edges are followed to their placeholder node (a dead end) so the gap is visible. */
export function expand(ix: Index, starts: string[], dir: Direction, depth: number, f: Filters): { nodes: Set<string>; edges: Set<string>; truncated: boolean } {
  const nodes = new Set(starts), edges = new Set<string>()
  let frontier = [...starts]
  let truncated = false
  for (let d = 0; d < depth && frontier.length; d++) {
    const next: string[] = []
    for (const id of frontier) {
      for (const { edge, other } of step(ix, id, dir, f)) {
        edges.add(edge.id)
        if (!nodes.has(other)) { nodes.add(other); next.push(other) }
      }
    }
    frontier = next
  }
  // were there more neighbours beyond the depth limit?
  for (const id of frontier) if (step(ix, id, dir, f).some((s) => !nodes.has(s.other))) truncated = true
  return { nodes, edges, truncated }
}

/** Edges to draw: those between visible nodes that pass the edge filters. */
export function visibleEdges(ix: Index, visible: Set<string>, f: Filters): GEdge[] {
  const out: GEdge[] = []
  for (const id of visible) for (const e of ix.out.get(id) ?? []) if (visible.has(e.target) && edgePasses(e, f)) out.push(e)
  return out
}

export function visibleNodes(ix: Index, visible: Set<string>, f: Filters): GNode[] {
  return [...visible].map((id) => ix.nodes.get(id)).filter((n): n is GNode => !!n && nodePasses(n, f))
}

/** Case-insensitive search by name (or id). Ranking: exact name, name prefix, last-segment match, substring. */
export function search(ix: Index, query: string, f: Filters, limit = 20): GNode[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const scored: { n: GNode; s: number }[] = []
  for (const n of ix.nodes.values()) {
    if (!nodePasses(n, f)) continue
    const name = n.name.toLowerCase(), last = name.split(/[.\s>]/).filter(Boolean).pop() ?? name
    let s = -1
    if (name === q) s = 0
    else if (name.startsWith(q)) s = 1
    else if (last === q || last.startsWith(q)) s = 2
    else if (name.includes(q)) s = 3
    else if (n.id.toLowerCase().includes(q)) s = 4
    if (s >= 0) scored.push({ n, s })
  }
  return scored.sort((a, b) => a.s - b.s || a.n.name.length - b.n.name.length || a.n.name.localeCompare(b.n.name)).slice(0, limit).map((x) => x.n)
}

export const directionLabel = (d: Direction) =>
  d === 'downstream' ? 'Downstream: consumers (who depends on this)' : 'Upstream: dependencies (what this depends on)'

export function distinctValues(ix: Index, key: 'repo' | 'kind'): string[] {
  return [...new Set([...ix.nodes.values()].map((n) => n[key]))].sort()
}
