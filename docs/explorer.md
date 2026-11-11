# Local explorer

A read-only, local web UI for the dependency graph (React + TypeScript + Vite, Cytoscape.js). It shows **structure only**: static-analysis evidence from a small
sample that includes clearly marked synthetic additions. It says nothing about real code bases.

## Run
```
python -m cdi.export                # writes out/explorer/ (git-ignored)
cd frontend && npm ci && npm run build && npm run preview     # http://127.0.0.1:4173
```
`backend/src/cdi/export.py` reads the baseline through a **read-only** Neo4j session when `NEO4J_PASSWORD` is set (and the store has a baseline), otherwise from the scan/linker files in
`out/graph`. It also copies the impact reports (`out/report-*.md|json`) and the latest simulated `out/pr-comment.md` / `out/pr-status.json`. It overwrites but never deletes files.
`npm run dev` serves the same data with hot reload. The data directory can be changed with `EXPLORER_DATA_DIR`. For static hosting, copy `out/explorer` to `dist/data`.

## Using it
* **Search** by name (exact, prefix, last segment, substring). Pick a result to put it on the canvas.
* **Expand**: click a node (or "Expand selected"). The **depth** slider sets how many hops; the note under it says when the expansion stopped at the depth limit.
* **Direction** follows `docs/schema.md`. Edges mean "A depends on B".
  **Downstream: affected by this (consumers)** - who depends on this node; follows edges in reverse; the impact of a change.
  **Upstream: depends on (dependencies)** - what this node depends on; follows edges forward; root-cause tracing.
  A screen's SQL tables are therefore its *upstream* dependencies even though they are drawn lower in the picture.
* **Filters**: repo, node kind, confidence, and whether `USES_TYPE` edges are shown. Filtered-out nodes are not traversed.
* **Edge style by confidence** (never colour alone): `CONFIRMED_STATIC` solid blue with a triangle head; `INFERRED` dashed orange with a vee head; `UNRESOLVED` dotted red with a bar head.
  Node shape encodes kind, colour encodes repo, a **double border** marks synthetic code, and **UNRESOLVED / not-found** nodes are red dashed octagons with a cross.
* **Side panel**: kind, repo, file:line, commit, a *synthetic* badge, the edge's evidence line, analysis method, **reason** (why unresolved / why not confirmed), and a link to the exact file
  and line on GitHub built from the base URL in `frontend/public/explorer.config.json` and the edge's `commit_id` (the link only works if that commit exists in the target repository).
* **Reports** lists and renders the impact reports (Markdown). **PR comment preview** shows `pr-comment.md` and `pr-status.json`, labelled *simulated*.
* A text list of the visible nodes sits under the canvas, so the page is usable without reading the drawing.

## Quality checks (as run when this was built)
* Dependency versions are pinned exactly in `frontend/package.json` and `package-lock.json`. `npm audit`: 0 vulnerabilities (all and production-only).
* `npm run licenses` (reads `node_modules`): production tree 105 MIT + 1 ISC; dev tooling also Apache-2.0, BSD-3-Clause, and MPL-2.0 for `lightningcss` (a build-time CSS tool that does not ship in the app).
* No telemetry and no external CDNs: the built bundle references only XML namespace identifiers; the smoke test fails if the page requests anything outside `127.0.0.1`.
* Tests: `npm test` (Vitest: direction, depth, filters, search, GitHub links, labels) and `npm run test:e2e` (Playwright smoke test against the built app; it runs `backend/src/cdi/export.py` first).
