import { useEffect, useMemo, useState } from 'react'
import { buildIndex, loadGraph, type GraphData, type Index } from './lib/graph'
import { loadLinkConfig, type LinkConfig } from './lib/github'
import GraphPage from './components/GraphPage'
import ReportsPage from './components/ReportsPage'
import PrCommentPage from './components/PrCommentPage'

type Page = 'graph' | 'reports' | 'pr'
const pageFromHash = (): Page => (location.hash.startsWith('#/reports') ? 'reports' : location.hash.startsWith('#/pr') ? 'pr' : 'graph')

export default function App() {
  const [page, setPage] = useState<Page>(pageFromHash())
  const [data, setData] = useState<GraphData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [linkCfg, setLinkCfg] = useState<LinkConfig | null>(null)
  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  useEffect(() => {
    loadGraph().then(setData).catch((e) => setError(String(e.message ?? e)))
    loadLinkConfig().then(setLinkCfg)
  }, [])
  const ix: Index | null = useMemo(() => (data ? buildIndex(data) : null), [data])

  return (
    <div className="app">
      <header className="topbar">
        <h1>Dependency explorer</h1>
        <nav aria-label="Pages">
          <a href="#/graph" aria-current={page === 'graph' ? 'page' : undefined}>Graph</a>
          <a href="#/reports" aria-current={page === 'reports' ? 'page' : undefined}>Reports</a>
          <a href="#/pr" aria-current={page === 'pr' ? 'page' : undefined}>PR comment preview</a>
        </nav>
        {data && (
          <span className="meta" title={data.meta.notice}>
            {data.meta.counts.nodes} nodes · {data.meta.counts.edges} edges · source: {data.meta.source}
            {data.meta.baseline?.commits && <> · baseline {Object.entries(data.meta.baseline.commits).map(([r, c]) => `${r} ${c.slice(0, 8)}`).join(', ')}</>}
          </span>
        )}
      </header>
      <div className="banner" role="note">Structure only. Synthetic sample data: static-analysis evidence from a small sample that includes clearly marked synthetic additions; it says nothing about real code.</div>
      {error && <div className="error" role="alert">{error}</div>}
      {page === 'graph' && (ix ? <GraphPage ix={ix} linkCfg={linkCfg} /> : !error && <p className="pad">Loading graph…</p>)}
      {page === 'reports' && <ReportsPage />}
      {page === 'pr' && <PrCommentPage />}
    </div>
  )
}
