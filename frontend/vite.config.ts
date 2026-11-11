import { defineConfig } from 'vitest/config'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
// The explorer reads generated data (never committed) from out/explorer, written by `python -m cdi.export`.
const dataDir = path.resolve(process.env.EXPLORER_DATA_DIR ?? path.join(here, '../out/explorer'))
const types: Record<string, string> = { '.json': 'application/json', '.md': 'text/markdown; charset=utf-8' }

function serveData(): Plugin {
  const mw = (req: { url?: string }, res: any, next: () => void) => {
    if (!req.url?.startsWith('/data/')) return next()
    const rel = decodeURIComponent(req.url.slice('/data/'.length).split('?')[0])
    const file = path.resolve(dataDir, rel)
    if (!file.startsWith(dataDir + path.sep)) { res.statusCode = 403; return res.end('forbidden') }   // no path traversal
    fs.readFile(file, (err, buf) => {
      if (err) { res.statusCode = 404; return res.end('not found') }
      res.setHeader('Content-Type', types[path.extname(file)] ?? 'application/octet-stream')
      res.setHeader('Cache-Control', 'no-store')
      res.end(buf)
    })
  }
  return { name: 'serve-explorer-data', configureServer: (s) => { s.middlewares.use(mw) }, configurePreviewServer: (s) => { s.middlewares.use(mw) } }
}

export default defineConfig({ base: './', plugins: [react(), serveData()], test: { include: ['src/**/*.test.ts'], environment: 'node' }, server: { host: '127.0.0.1', port: 5173 }, preview: { host: '127.0.0.1' } })
