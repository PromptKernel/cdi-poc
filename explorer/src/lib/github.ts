import type { GraphMeta } from './graph'

export interface LinkConfig { githubBaseUrl: string; linkTemplate: string }

/** Link to the exact file and line on GitHub at the given commit. Built from the configurable base URL, the commit id, and the logical repo's
 *  folder (config/repos.yml). Returns null when anything needed is missing (no commit, no file, no base URL). */
export function githubLink(cfg: LinkConfig | null, meta: GraphMeta | null, repo: string, file: string | null, line: number | null, commit: string | null): string | null {
  if (!cfg?.githubBaseUrl || !meta || !file || !commit || !/^[0-9a-f]{7,40}$/.test(commit)) return null
  const repoPath = meta.repos[repo]?.path
  if (!repoPath) return null
  const enc = (p: string) => p.split('/').map(encodeURIComponent).join('/')
  return cfg.linkTemplate
    .replace('{base}', cfg.githubBaseUrl.replace(/\/+$/, ''))
    .replace('{commit}', commit)
    .replace('{repoPath}', enc(repoPath))
    .replace('{file}', enc(file))
    .replace('{line}', String(line ?? 1))
}

export async function loadLinkConfig(url = 'explorer.config.json'): Promise<LinkConfig | null> {
  try {
    const r = await fetch(url, { cache: 'no-store' })
    return r.ok ? ((await r.json()) as LinkConfig) : null
  } catch {
    return null
  }
}
