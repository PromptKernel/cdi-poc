import { CONFIDENCE_STYLE, REPO_COLOR } from '../lib/style'

const DASH: Record<string, string> = { solid: '', dashed: '9 5', dotted: '2 5' }

export default function Legend() {
  return (
    <section className="legend" aria-label="Legend">
      <h2>Legend</h2>
      <p className="dim">Edge: A → B means A depends on B. Confidence differs by line style, colour and arrowhead, not colour alone.</p>
      <ul>
        {Object.entries(CONFIDENCE_STYLE).map(([k, s]) => (
          <li key={k}>
            <svg width="64" height="14" aria-hidden="true">
              <line x1="2" y1="7" x2={k === 'UNRESOLVED' ? 50 : 56} y2="7" stroke={s.color} strokeWidth={s.width} strokeDasharray={DASH[s.line]} />
              {k === 'CONFIRMED_STATIC' && <polygon points="56,7 48,3 48,11" fill={s.color} />}
              {k === 'INFERRED' && <polyline points="48,2 56,7 48,12" fill="none" stroke={s.color} strokeWidth="2" />}
              {k === 'UNRESOLVED' && <line x1="54" y1="1" x2="54" y2="13" stroke={s.color} strokeWidth="3" />}
            </svg>
            <span><b>{k}</b>: {s.line}, {s.label}</span>
          </li>
        ))}
      </ul>
      <ul>
        <li><span className="swatch unres" aria-hidden="true">✕</span> <b>UNRESOLVED / not found</b>: octagon, red dashed border (reason in the side panel)</li>
        <li><span className="swatch syn" aria-hidden="true" /> <b>Synthetic</b>: double border (code written for this PoC)</li>
        {Object.entries(REPO_COLOR).map(([r, c]) => <li key={r}><span className="swatch" style={{ borderColor: c, background: c + '2e' }} aria-hidden="true" /> repo <b>{r}</b> (colour); node shape = node kind</li>)}
      </ul>
    </section>
  )
}
