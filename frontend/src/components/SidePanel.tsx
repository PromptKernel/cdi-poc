import type { Index } from '../lib/graph'
import { githubLink, type LinkConfig } from '../lib/github'
import type { Selection } from './GraphPage'

const Badge = ({ children, tone }: { children: React.ReactNode; tone?: string }) => <span className={`badge ${tone ?? ''}`}>{children}</span>

export default function SidePanel({ ix, selection, linkCfg, onSelect }: { ix: Index; selection: Selection; linkCfg: LinkConfig | null; onSelect: (s: Selection) => void }) {
  const meta = ix.data.meta
  if (!selection) return <div className="panel"><h2>Details</h2><p className="dim">Select a node or an edge.</p></div>

  if (selection.type === 'edge') {
    const e = ix.edges.get(selection.id)
    if (!e) return null
    const s = ix.nodes.get(e.source), t = ix.nodes.get(e.target)
    const link = githubLink(linkCfg, meta, e.repo, e.source_file, e.line, e.commit_id)
    return (
      <div className="panel" data-testid="edge-panel">
        <h2>Edge · {e.type}</h2>
        <p><Badge tone={e.confidence}>{e.confidence}</Badge> {e.synthetic && <Badge tone="syn">synthetic</Badge>}</p>
        <dl>
          <dt>From (depends on →)</dt><dd><button className="link" onClick={() => onSelect({ type: 'node', id: e.source })}>{s?.name ?? e.source}</button></dd>
          <dt>To</dt><dd><button className="link" onClick={() => onSelect({ type: 'node', id: e.target })}>{t?.name ?? e.target}</button></dd>
          <dt>Evidence location</dt><dd><code>{e.repo}:{e.source_file}:{e.line}</code> {link ? <a href={link} target="_blank" rel="noreferrer noopener">view on GitHub ↗</a> : <span className="dim">(no link: missing commit or base URL)</span>}</dd>
          <dt>Source line</dt><dd>{e.evidence ? <code className="block">{e.evidence}</code> : <span className="dim">none recorded</span>}</dd>
          <dt>Analysis method</dt><dd><code>{e.analysis_method}</code></dd>
          <dt>Commit</dt><dd><code>{e.commit_id}</code></dd>
          {e.reason && <><dt>Reason ({e.confidence === 'UNRESOLVED' ? 'why unresolved' : 'why not confirmed'})</dt><dd className="reason">{e.reason}</dd></>}
          {Object.keys(e.attrs).length > 0 && <><dt>Attributes</dt><dd><code className="block">{JSON.stringify(e.attrs, null, 1)}</code></dd></>}
        </dl>
      </div>
    )
  }

  const n = ix.nodes.get(selection.id)
  if (!n) return null
  const commit = meta.baseline?.commits?.[n.repo] ?? null
  const link = githubLink(linkCfg, meta, n.repo, n.file, n.line, commit)
  const incident = [...(ix.out.get(n.id) ?? []), ...(ix.inn.get(n.id) ?? [])]
  const unresolvedHere = incident.filter((e) => e.confidence === 'UNRESOLVED')
  return (
    <div className="panel" data-testid="node-panel">
      <h2>{n.name}</h2>
      <p><Badge>{n.kind}</Badge> <Badge>{n.repo}</Badge> {n.synthetic && <Badge tone="syn">synthetic</Badge>} {n.kind === 'UNRESOLVED' && <Badge tone="UNRESOLVED">unresolved / not found</Badge>}</p>
      <dl>
        <dt>Location</dt>
        <dd>{n.file ? <><code>{n.repo}:{n.file}:{n.line}{n.end_line && n.end_line !== n.line ? `–${n.end_line}` : ''}</code> {link ? <a href={link} target="_blank" rel="noreferrer noopener">view on GitHub ↗</a> : <span className="dim">(no link)</span>}</> : <span className="dim">no source location (a reference or placeholder node)</span>}</dd>
        <dt>Commit (baseline, {n.repo})</dt><dd>{commit ? <code>{commit}</code> : <span className="dim">unknown</span>}</dd>
        {n.kind === 'UNRESOLVED' && <><dt>Why</dt><dd className="reason">{unresolvedHere[0]?.reason ?? 'no reason recorded'}</dd></>}
        {Object.keys(n.attrs).length > 0 && <><dt>Attributes</dt><dd><code className="block">{JSON.stringify(n.attrs, null, 1)}</code></dd></>}
      </dl>
      <h3>Edges ({incident.length})</h3>
      <ul className="edges">
        {incident.map((e) => (
          <li key={e.id}>
            <button className="link" onClick={() => onSelect({ type: 'edge', id: e.id })}>
              <Badge tone={e.confidence}>{e.confidence === 'CONFIRMED_STATIC' ? 'C' : e.confidence === 'INFERRED' ? 'I' : 'U'}</Badge> {e.type} {e.source === n.id ? '→' : '←'} {ix.nodes.get(e.source === n.id ? e.target : e.source)?.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
