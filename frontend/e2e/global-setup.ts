import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Regenerate out/explorer from the baseline (Neo4j if NEO4J_PASSWORD is set, otherwise the scan/linker files in out/graph).
export default async function setup() {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')       // the repository that holds config/ and out/ (interim; see the fixture flow in a later phase)
  const py = process.env.PYTHON ?? path.join(root, '.venv/bin/python')
  const out = execFileSync(py, ['-m', 'cdi.export'], { cwd: root, encoding: 'utf8' })
  console.log('[e2e setup] export:', out.trim())
}
