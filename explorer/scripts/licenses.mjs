// Lists the licence of every installed package (production and development trees separately) and fails if one is outside the allow-list.
// No network access, no dependencies: it reads node_modules/*/package.json and `npm ls --all --json`.
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const ALLOWED = ['MIT', 'ISC', 'BSD-2-Clause', 'BSD-3-Clause', 'Apache-2.0', '0BSD', 'BlueOak-1.0.0', 'CC0-1.0', 'Unlicense', 'Python-2.0', 'MIT-0', 'CC-BY-4.0']
const DEV_ONLY_ALLOWED = ['MPL-2.0']   // weak copyleft (file-level); accepted ONLY for build-time tooling that is not shipped in the built app
const installed = (name) => fs.existsSync(path.join('node_modules', name, 'package.json'))
const lic = (name) => {
  try {
    const p = JSON.parse(fs.readFileSync(path.join('node_modules', name, 'package.json'), 'utf8'))
    const l = p.license ?? (Array.isArray(p.licenses) ? p.licenses.map((x) => x.type).join(' OR ') : p.licenses?.type)
    return typeof l === 'object' ? l.type : l ?? 'UNKNOWN'
  } catch { return 'UNREADABLE' }
}
const walk = (tree, acc = new Map()) => { for (const [n, d] of Object.entries(tree.dependencies ?? {})) { acc.set(n, d.version); walk(d, acc) } return acc }
const ls = (omit) => JSON.parse(execFileSync('npm', ['ls', '--all', '--json', ...(omit ? ['--omit=dev'] : [])], { encoding: 'utf8', maxBuffer: 1 << 28 }))
const ok = (l, devOnly) => String(l).split(/\s+OR\s+|[()]/).map((x) => x.trim()).filter(Boolean).some((x) => ALLOWED.includes(x) || (devOnly && DEV_ONLY_ALLOWED.includes(x)))

let bad = 0
for (const [title, omit] of [['PRODUCTION dependencies (ship in the built app)', true], ['ALL dependencies incl. dev tooling', false]]) {
  const m = walk(ls(omit))
  const by = new Map()
  const notInstalled = [...m.keys()].filter((n) => !installed(n))      // optional binaries for other platforms are listed by npm but not installed here
  for (const n of m.keys()) { if (!installed(n)) continue; const l = lic(n); by.set(l, [...(by.get(l) ?? []), n]) }
  console.log(`\n${title}: ${m.size - notInstalled.length} installed packages (${notInstalled.length} optional packages for other platforms are not installed)`)
  for (const [l, names] of [...by].sort((a, b) => b[1].length - a[1].length)) {
    const fine = ok(l, !omit)
    console.log(`  ${String(names.length).padStart(4)}  ${l}${fine ? (ALLOWED.includes(l) ? '' : '   (accepted: dev/build-time only)') : '   <-- NOT IN ALLOW-LIST'}${names.length <= 4 && l !== 'MIT' ? '  ' + names.join(', ') : ''}`)
    if (!fine) bad += names.length
  }
}
console.log(`\nallow-list: ${ALLOWED.join(', ')}`)
if (bad) { console.error(`${bad} package(s) outside the allow-list`); process.exit(1) }
