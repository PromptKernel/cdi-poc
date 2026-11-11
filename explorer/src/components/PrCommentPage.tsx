import { useEffect, useState } from 'react'
import Markdown from './Markdown'

// The first line is the stable marker (an HTML comment) that lets a re-run find and update its own thread; show it as a note, render the rest.
const splitMarker = (t: string) => { const m = t.match(/^<!--\s*(.*?)\s*-->\s*\n?/); return m ? { marker: m[1], body: t.slice(m[0].length) } : { marker: null, body: t } }

export default function PrCommentPage() {
  const [md, setMd] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    fetch('data/pr/index.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`PR files not found (${r.status}); run python tools/export_graph.py`))))
      .then(async (idx) => {
        if (idx.comment) setMd(await (await fetch(`data/${idx.comment}`, { cache: 'no-store' })).text())
        if (idx.status) setStatus(JSON.stringify(await (await fetch(`data/${idx.status}`, { cache: 'no-store' })).json(), null, 2))
      }).catch((e) => setErr(String(e.message ?? e)))
  }, [])
  if (err) return <div className="error" role="alert">{err}</div>
  return (
    <div className="pr">
      <p className="sim" role="note"><b>Simulated.</b> Nothing was posted anywhere. This is the local file output of <code>pipeline/run_pr.sh</code>; the Azure DevOps payload shapes follow the public REST docs and were <b>not tested against a real service</b>.</p>
      <div className="prcols">
        <section aria-label="PR comment"><h2>pr-comment.md</h2>{md === null ? <p className="dim">No pr-comment.md found. Run pipeline/run_pr.sh and export again.</p> : (() => { const { marker, body } = splitMarker(md); return <>{marker && <p className="marker dim">Marker (used to update this comment in place on every push): <code>{marker}</code></p>}<Markdown text={body} /></>})()}</section>
        <section aria-label="PR status"><h2>pr-status.json</h2>{status === null ? <p className="dim">No pr-status.json found.</p> : <pre className="json">{status}</pre>}</section>
      </div>
    </div>
  )
}
