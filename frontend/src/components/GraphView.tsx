import { useEffect, useRef } from 'react'
import cytoscape, { type Core } from 'cytoscape'
import dagre from 'cytoscape-dagre'
import type { GEdge, GNode, Index } from '../lib/graph'
import { KIND_SHAPE, REPO_COLOR, stylesheet } from '../lib/style'
import type { Selection } from './GraphPage'

let registered = false
function register() { if (!registered) { cytoscape.use(dagre as never); registered = true } }

// On-canvas label: drop namespaces from C# names (the side panel always shows the full name)
export const shortName = (name: string): string => {
  const paren = name.indexOf('(')
  const head = paren >= 0 ? name.slice(0, paren) : name
  const tail = paren >= 0 ? name.slice(paren) : ''
  if (!/^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*){2,}$/.test(head)) return name.length > 52 ? `…${name.slice(-50)}` : name
  const parts = head.split('.')
  return `${parts.slice(-2).join('.')}${tail.length > 26 ? tail.slice(0, 24) + '…)' : tail}`
}
const label = (n: GNode) => (n.kind === 'UNRESOLVED' ? `✕ ${n.name}` : shortName(n.name))

export default function GraphView({ ix, nodes, edges, selection, onSelect }: { ix: Index; nodes: GNode[]; edges: GEdge[]; selection: Selection; onSelect: (s: Selection) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const cy = useRef<Core | null>(null)
  const cb = useRef(onSelect)
  cb.current = onSelect

  useEffect(() => {
    register()
    const c = cytoscape({ container: box.current, style: stylesheet(), wheelSensitivity: 0.25, minZoom: 0.15, maxZoom: 3 })
    c.on('tap', 'node', (ev) => cb.current({ type: 'node', id: ev.target.id() }))
    c.on('tap', 'edge', (ev) => cb.current({ type: 'edge', id: ev.target.id() }))
    c.on('tap', (ev) => { if (ev.target === c) cb.current(null) })
    cy.current = c
    ;(window as unknown as { __cy?: Core }).__cy = c   // read-only debugging/test handle (local tool)
    const ro = new ResizeObserver(() => { c.resize(); if (c.nodes().length) c.fit(undefined, 28) })
    if (box.current) ro.observe(box.current)
    return () => { ro.disconnect(); c.destroy(); cy.current = null }
  }, [])

  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.batch(() => {
      c.elements().remove()
      c.add([
        ...nodes.map((n) => ({ group: 'nodes' as const, data: { id: n.id, label: label(n), kind: n.kind, synthetic: n.synthetic, color: n.kind === 'UNRESOLVED' ? '#b91c1c' : REPO_COLOR[n.repo] ?? '#6b7280', shape: KIND_SHAPE[n.kind] ?? 'ellipse' } })),
        ...edges.map((e) => ({ group: 'edges' as const, data: { id: e.id, source: e.source, target: e.target, type: e.type, confidence: e.confidence } })),
      ])
    })
    c.resize()                                           // the container may have changed size since creation: fit against its real size
    if (nodes.length) c.layout({ name: 'dagre', rankDir: 'TB', nodeSep: 36, rankSep: 70, animate: false, fit: true, padding: 28 } as never).run()
  }, [nodes, edges])

  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.elements().unselect()
    if (selection) c.getElementById(selection.id).select()
  }, [selection, nodes, edges])

  return (
    <div className="graphbox">
      <div ref={box} className="cy" role="img" aria-label={`Dependency graph with ${nodes.length} nodes and ${edges.length} edges. A text list of the visible nodes follows the graph.`} data-testid="graph-canvas" />
      {nodes.length === 0 && <p className="empty">Search for a node (for example FetchEmployeeComponent) to start.</p>}
      <span hidden data-testid="graph-counts">{nodes.length}/{edges.length}</span>
      <span hidden>{ix.data.meta.counts.nodes}</span>
    </div>
  )
}
