import { useEffect, useState } from 'react'
import Markdown from './Markdown'

interface Entry { name: string; md: string; json: string | null; modified: string; summary?: { objects: number; pr: string; labels: string[]; warnings: number } }

export default function ReportsPage() {
  const [list, setList] = useState<Entry[] | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    fetch('data/reports/index.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`reports index not found (${r.status}); run python tools/export_graph.py`))))
      .then((d) => { setList(d.reports); if (d.reports[0]) setSel(d.reports[0].name) }).catch((e) => setErr(String(e.message ?? e)))
  }, [])
  useEffect(() => {
    const e = list?.find((x) => x.name === sel)
    if (!e) return
    fetch(`data/${e.md}`, { cache: 'no-store' }).then((r) => r.text()).then(setText).catch((x) => setErr(String(x)))
  }, [sel, list])
  if (err) return <div className="error" role="alert">{err}</div>
  if (!list) return <p className="pad">Loading…</p>
  return (
    <div className="reports">
      <aside aria-label="Impact reports">
        <h2>Impact reports ({list.length})</h2>
        {list.length === 0 && <p className="dim">No reports found in out/. Run the impact CLI (python -m impact.cli) and export again.</p>}
        <ul>
          {list.map((r) => (
            <li key={r.name}>
              <button aria-pressed={sel === r.name} onClick={() => setSel(r.name)}><b>{r.name}</b>
                <span className="dim"> {r.summary ? `${r.summary.objects} object(s)${r.summary.labels.length ? ' · ' + r.summary.labels.join('/') : ' · no label'}` : ''}</span></button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="doc" aria-label="Report">
        <p className="dim">Impact reports are generated for synthetic demo changes. Every claim in a report cites a stored edge (file:line, method, commit).</p>
        <Markdown text={text} />
      </section>
    </div>
  )
}
