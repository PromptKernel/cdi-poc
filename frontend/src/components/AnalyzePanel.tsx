import { describeBaseline } from '../lib/analyze'
import type { GraphMeta } from '../lib/graph'
import type { DataSource } from '../lib/source'

/** What the loaded baseline is: where it came from, which commit of every logical repo it describes, when it was loaded and its store schema version. */
export default function AnalyzePanel({ meta, source }: { meta: GraphMeta; source: DataSource }) {
  const f = describeBaseline(meta)
  return (
    <div className="analyze" data-testid="analyze-panel">
      <h2>Baseline</h2>
      <dl>
        <dt>Data source</dt><dd data-testid="analyze-source">{source.label}</dd>
        <dt>Schema version</dt><dd data-testid="analyze-schema">{f.schemaVersion}</dd>
        <dt>Loaded at</dt><dd data-testid="analyze-loaded">{f.loadedAt}</dd>
        <dt>Built by</dt><dd>{f.mode}</dd>
        <dt>Contents</dt><dd>{f.counts}</dd>
      </dl>
      <h3>Commit of each logical repo</h3>
      <table aria-label="Baseline commits">
        <thead><tr><th>Repo</th><th>Kind</th><th>Folder</th><th>Commit</th></tr></thead>
        <tbody>
          {f.rows.map((r) => (
            <tr key={r.repo}><td>{r.repo}</td><td>{r.kind}</td><td><code>{r.path}</code></td><td>{r.commit ? <code data-testid={`commit-${r.repo}`}>{r.commit}</code> : <span className="dim">{r.short}</span>}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="dim">This is the graph of the base branch. A pull request is compared with it by <code>cdi pr</code> or the GitHub flow; the results appear under Reports.
        If a PR&apos;s merge-base differs from these commits the report says how far behind the baseline is.</p>
    </div>
  )
}
