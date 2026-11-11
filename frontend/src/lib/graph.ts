export type Confidence = 'CONFIRMED_STATIC' | 'INFERRED' | 'UNRESOLVED'
export const CONFIDENCES: Confidence[] = ['CONFIRMED_STATIC', 'INFERRED', 'UNRESOLVED']

export interface GNode {
  id: string; kind: string; name: string; repo: string; file: string | null; line: number | null; end_line: number | null
  synthetic: boolean; attrs: Record<string, unknown>
}
export interface GEdge {
  id: string; type: string; source: string; target: string; confidence: Confidence; source_file: string; line: number; column: number | null
  commit_id: string; repo: string; synthetic: boolean; reason: string | null; evidence: string; analysis_method: string; attrs: Record<string, unknown>
}
export interface GraphMeta {
  generated_at: string; source: string; notice: string; counts: { nodes: number; edges: number }
  baseline: { commits: Record<string, string>; loaded_at: string | null; mode: string | null } | null
  repos: Record<string, { path: string; kind: string }>
}
export interface GraphData { meta: GraphMeta; nodes: GNode[]; edges: GEdge[] }

export interface Index {
  data: GraphData
  nodes: Map<string, GNode>
  edges: Map<string, GEdge>
  out: Map<string, GEdge[]>   // edges whose SOURCE is the key (the key depends on the target)
  inn: Map<string, GEdge[]>   // edges whose TARGET is the key (the source depends on the key)
}

export function buildIndex(data: GraphData): Index {
  const nodes = new Map(data.nodes.map((n) => [n.id, n]))
  const edges = new Map(data.edges.map((e) => [e.id, e]))
  const out = new Map<string, GEdge[]>(), inn = new Map<string, GEdge[]>()
  for (const e of data.edges) {
    ;(out.get(e.source) ?? out.set(e.source, []).get(e.source)!).push(e)
    ;(inn.get(e.target) ?? inn.set(e.target, []).get(e.target)!).push(e)
  }
  return { data, nodes, edges, out, inn }
}

export async function loadGraph(url = 'data/graph.json'): Promise<GraphData> {
  const r = await fetch(url, { cache: 'no-store' })
  if (!r.ok) throw new Error(`could not load ${url} (${r.status}). Run: python tools/export_graph.py`)
  return (await r.json()) as GraphData
}
