import type { StylesheetJson } from 'cytoscape'

// Confidence is encoded THREE ways so it never relies on colour alone: line style, line width/colour, and arrow shape.
export const CONFIDENCE_STYLE = {
  CONFIRMED_STATIC: { color: '#1f4e9c', line: 'solid', width: 3, arrow: 'triangle', label: 'Confirmed static link' },
  INFERRED: { color: '#b45309', line: 'dashed', width: 2.5, arrow: 'vee', label: 'Inferred (depends on runtime or a heuristic)' },
  UNRESOLVED: { color: '#b91c1c', line: 'dotted', width: 2.5, arrow: 'tee', label: 'Unresolved / not found' },
} as const

export const REPO_COLOR: Record<string, string> = { web: '#2563eb', api: '#0f766e', db: '#7c3aed', linker: '#6b7280' }
export const KIND_SHAPE: Record<string, string> = {
  UI_COMPONENT: 'round-rectangle', UI_SERVICE_METHOD: 'rectangle', UI_MODEL: 'tag', HTTP_REQUEST: 'diamond', API_ENDPOINT: 'hexagon',
  SERVICE_METHOD: 'round-pentagon', DATA_ACCESS_METHOD: 'round-pentagon', METHOD: 'ellipse', INTERFACE_METHOD: 'round-diamond',
  SQL_REF: 'round-tag', SQL_PROC: 'barrel', SQL_VIEW: 'round-heptagon', SQL_TABLE: 'cut-rectangle', SQL_COLUMN: 'ellipse', TEST: 'round-triangle', UNRESOLVED: 'octagon',
}

export const stylesheet = (): StylesheetJson => [
  { selector: 'node', style: { label: 'data(label)', 'font-size': 11, 'text-wrap': 'ellipsis', 'text-max-width': '230px', 'text-valign': 'center', 'text-halign': 'center',
      color: '#111827', 'background-color': 'data(color)', 'background-opacity': 0.18, 'border-width': 2, 'border-color': 'data(color)', shape: 'data(shape)' as never,
      width: 'label', height: 'label', padding: '9px' } as never },
  // synthetic code: double border
  { selector: 'node[?synthetic]', style: { 'border-style': 'double', 'border-width': 4 } as never },
  // unresolved / not-found placeholders: distinct octagon, red dashed border, striped look
  { selector: 'node[kind = "UNRESOLVED"]', style: { 'background-color': '#fee2e2', 'background-opacity': 1, 'border-color': '#b91c1c', 'border-style': 'dashed', 'border-width': 3,
      color: '#7f1d1d', 'font-weight': 'bold' } as never },
  { selector: 'node:selected', style: { 'overlay-color': '#facc15', 'overlay-opacity': 0.35, 'overlay-padding': 7 } as never },
  { selector: 'node.focus', style: { 'border-width': 5 } as never },
  ...(Object.entries(CONFIDENCE_STYLE) as [keyof typeof CONFIDENCE_STYLE, (typeof CONFIDENCE_STYLE)[keyof typeof CONFIDENCE_STYLE]][]).map(([c, s]) => ({
    selector: `edge[confidence = "${c}"]`,
    style: { 'line-color': s.color, 'target-arrow-color': s.color, 'line-style': s.line, width: s.width, 'target-arrow-shape': s.arrow, 'curve-style': 'bezier', 'arrow-scale': 1.3 } as never,
  })),
  { selector: 'edge', style: { label: 'data(type)', 'font-size': 8, color: '#374151', 'text-rotation': 'none', 'text-background-color': '#ffffff', 'text-background-opacity': 0.9, 'text-background-padding': '2px', 'text-margin-x': 6 } as never },
  { selector: 'edge:selected', style: { 'overlay-color': '#facc15', 'overlay-opacity': 0.4, 'overlay-padding': 6 } as never },
]
