import { useEffect, useState } from 'react'
import Markdown from './Markdown'
import type { DataSource, ReportEntry as Entry } from '../lib/source'

export default function ReportsPage({ source }: { source: DataSource }) {
  const [list, setList] = useState<Entry[] | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    source.reportsIndex().then((reports) => { setList(reports); if (reports[0]) setSel(reports[0].name) }).catch((e) => setErr(String(e.message ?? e)))
  }, [source])
  useEffect(() => {
    const e = list?.find((x) => x.name === sel)
    if (!e) return
    source.text(e.md).then(setText).catch((x) => setErr(String(x.message ?? x)))
  }, [sel, list, source])
  if (err) return <div className="error" role="alert">{err}</div>
  if (!list) return <p className="pad">Loading…</p>
  return (
    <div className="reports">
      <aside aria-label="Impact reports">
        <h2>Impact reports ({list.length})</h2>
        {list.length === 0 && <p className="dim">No reports found in out/. Run `cdi pr` (or the GitHub flow) to create one.</p>}
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
