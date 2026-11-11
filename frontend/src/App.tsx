import { useCallback, useEffect, useMemo, useState } from 'react'
import { buildIndex, type GraphData, type Index } from './lib/graph'
import { loadLinkConfig, type LinkConfig } from './lib/github'
import { AuthError, getToken, loadRuntime, setToken } from './lib/runtime'
import { makeSource, type DataSource } from './lib/source'
import GraphPage from './components/GraphPage'
import ReportsPage from './components/ReportsPage'
import PrCommentPage from './components/PrCommentPage'
import AnalyzePanel from './components/AnalyzePanel'

type Page = 'graph' | 'analyze' | 'reports' | 'pr'
const pageFromHash = (): Page => (location.hash.startsWith('#/reports') ? 'reports' : location.hash.startsWith('#/pr') ? 'pr' : location.hash.startsWith('#/analyze') ? 'analyze' : 'graph')

export default function App() {
  const [page, setPage] = useState<Page>(pageFromHash())
  const [source, setSource] = useState<DataSource | null>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [needToken, setNeedToken] = useState(false)
  const [tokenInput, setTokenInput] = useState('')
  const [linkCfg, setLinkCfg] = useState<LinkConfig | null>(null)
  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const load = useCallback(async () => {
    setError(null)
    try {
      const rt = await loadRuntime()                           // config.json is read at run time, not baked into the build
      const src = makeSource(rt, fetch.bind(globalThis), getToken)
      setSource(src)
      setData(await src.loadGraph())
      setNeedToken(false)
    } catch (e) {
      if (e instanceof AuthError) setNeedToken(true)
      else setError(String((e as Error).message ?? e))
    }
  }, [])
  useEffect(() => { load(); loadLinkConfig().then(setLinkCfg) }, [load])
  const ix: Index | null = useMemo(() => (data ? buildIndex(data) : null), [data])

  return (
    <div className="app">
      <header className="topbar">
        <h1>Dependency explorer</h1>
        <nav aria-label="Pages">
          <a href="#/graph" aria-current={page === 'graph' ? 'page' : undefined}>Graph</a>
          <a href="#/analyze" aria-current={page === 'analyze' ? 'page' : undefined}>Analyze</a>
          <a href="#/reports" aria-current={page === 'reports' ? 'page' : undefined}>Reports</a>
          <a href="#/pr" aria-current={page === 'pr' ? 'page' : undefined}>PR comment preview</a>
        </nav>
        {source && <span className={`source ${source.kind}`} data-testid="data-source" data-kind={source.kind}>data source: {source.label}</span>}
        {data && (
          <span className="meta" title={data.meta.notice}>
            {data.meta.counts.nodes} nodes · {data.meta.counts.edges} edges
            {data.meta.baseline?.commits && <> · baseline {Object.entries(data.meta.baseline.commits).map(([r, c]) => `${r} ${c.slice(0, 8)}`).join(', ')}</>}
          </span>
        )}
      </header>
      <div className="banner" role="note" data-testid="notice">{data ? data.meta.notice : 'Structure only.'}</div>      {/* wording comes from the data (driven by the repository's synthetic flag), not from the page */}
      {needToken && (
        <form className="tokenform" onSubmit={(e) => { e.preventDefault(); setToken(tokenInput.trim()); setTokenInput(''); load() }}>
          <label>The API needs a bearer token <input type="password" autoComplete="off" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} aria-label="API token" /></label>
          <button type="submit">Use token</button> <span className="dim">kept for this browser tab only (sessionStorage)</span>
        </form>
      )}
      {error && <div className="error" role="alert">{error}</div>}
      {page === 'graph' && (ix ? <GraphPage ix={ix} linkCfg={linkCfg} /> : !error && !needToken && <p className="pad">Loading graph…</p>)}
      {page === 'analyze' && (data && source ? <AnalyzePanel meta={data.meta} source={source} /> : !error && !needToken && <p className="pad">Loading…</p>)}
      {page === 'reports' && source && <ReportsPage source={source} />}
      {page === 'pr' && source && <PrCommentPage source={source} />}
    </div>
  )
}
