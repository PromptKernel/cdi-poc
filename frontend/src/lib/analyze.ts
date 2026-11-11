import type { GraphMeta } from './graph'

export interface RepoRow { repo: string; kind: string; path: string; commit: string | null; short: string }
export interface Freshness { schemaVersion: string; mode: string; loadedAt: string; counts: string; rows: RepoRow[] }

/** What the Analyze panel shows about the baseline: per-repo commit ids, load time and schema version. Missing facts say so instead of being invented. */
export function describeBaseline(meta: GraphMeta): Freshness {
  const b = meta.baseline
  const repos = Object.keys({ ...meta.repos, ...(b?.commits ?? {}) }).sort()
  const rows = repos.map((repo) => {
    const commit = b?.commits?.[repo] ?? null
    return { repo, kind: meta.repos[repo]?.kind ?? '?', path: meta.repos[repo]?.path ?? '?', commit, short: commit ? commit.slice(0, 8) : 'not recorded' }
  })
  return {
    schemaVersion: b?.schema_version != null ? String(b.schema_version) : 'not recorded',
    mode: b?.mode ?? 'not recorded',
    loadedAt: b?.loaded_at ?? 'not recorded',
    counts: `${meta.counts.nodes} nodes, ${meta.counts.edges} edges`,
    rows,
  }
}
