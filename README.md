# cdi-poc

A cross-layer dependency graph and PR impact proof of concept: static scanners for a frontend (TypeScript/Angular), an API
(C#/.NET) and SQL Server code emit one shared, evidence-backed graph schema.

**Status: milestone 3 of the PoC (schema, three scanners, cross-repo linker, Neo4j load, bidirectional trace, baseline runner, PR impact report).** CI wrapper,
explorer and evaluation are planned and not in this repository yet. See `LIMITATIONS.md`.

## What is real and what is synthetic
- `samples/*` start from an upstream MIT-licensed sample (Angular + ASP.NET Core + ADO.NET), see `NOTICE` and `docs/changes.md`.
- **The upstream sample has no SQL.** All SQL under `samples/db/synthetic`, the Department API (`samples/api/Synthetic`), the Department screen
  (`samples/web/src/synthetic`), **all tests**, and any regression scenarios added later are **synthetic**: written for this PoC.
  Scan output marks them `synthetic: true`. Results on them are not evidence of accuracy on real code.
- The "three repos" are **folders of this one git repository**; `config/repos.yml` maps each logical repo name to its folder.

## Licence
This repository has **no top-level licence file**. The upstream-derived sample code is MIT (`samples/web/LICENSE`,
`samples/api/LICENSE`, `samples/db/LICENSE`, credited in `NOTICE`). No licence is granted for the other files.

## Setup
Requirements: git, Node 20+, Python 3.10+, .NET 10 SDK, Docker (for Neo4j).
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
(cd scanners/ts-morph && npm ci)
```

## Run order
1. Commit your working tree. Scanners **refuse to run on uncommitted changes in the logical repo's folder**, so `commit_id` matches the scanned files.
2. `pipeline/scan_all.sh` - builds the .NET scanners, runs Roslyn/ts-morph/ScriptDom per logical repo, validates against
   `schema/graph.schema.json`. Output: `out/graph/{web,api,db}.json` (git-ignored).
3. Neo4j (local, Community): `export NEO4J_PASSWORD='<choose one>'` then `docker compose -f graph/docker-compose.yml up -d`
   (ports bound to localhost 7688/7475; the password is never stored in the repo).
4. `pipeline/link_and_load.sh` - links across repos (`out/graph/linked.json`: HTTP route -> API endpoint, SQL reference -> definition,
   test -> covered node) and loads everything into Neo4j.
5. Trace, in both directions, with file:line evidence for every hop:
   `.venv/bin/python -m impact.trace FetchEmployeeComponent --kind UI_COMPONENT --direction forward --backend neo4j`
   `.venv/bin/python -m impact.trace dbo.tblEmployee --kind SQL_TABLE --direction reverse --backend neo4j`
   (`--backend memory` runs the same traversal without a database.) UNRESOLVED links are listed with their reason, never traversed.
6. Baseline runner (replaces steps 2 and 4 for day-to-day use): `.venv/bin/python -m pipeline.baseline full` (scan + link + replace the graph in Neo4j) or
   `.venv/bin/python -m pipeline.baseline incremental --from <rev> --to <rev>` (changed files only).
7. PR impact report for one branch: `.venv/bin/python -m impact.cli --target main --pr <branch>` writes `out/report-<branch>.md` / `.json`. See `docs/impact-report.md`.
8. `.venv/bin/python tools/show_workflow.py FetchEmployeeComponent spGetAllEmployees` - raw scanner edges with the cited source line re-read from disk.

## Demo branches and reports
Six synthetic scenarios (all local, never pushed): `pr-a-sp-body` (stored-procedure body), `pr-b-view` (view), `pr-c-ts-service` (TypeScript service method),
`pr-d-dynamic-sql` (proc containing dynamic SQL), `pr-e-delete-proc` (deleted procedure), `pr-f-route` (controller route no longer matches the frontend request).
```
export NEO4J_PASSWORD='<your password>'; docker compose -f graph/docker-compose.yml up -d
.venv/bin/python -m pipeline.baseline full                 # baseline graph of main in Neo4j
scripts/make_demo_branches.sh --reports neo4j              # from a clean main: recreate the branches, write out/report-<branch>.md/.json
```
Re-run the script after `main` moves (the branches are re-pointed to the new `main`); otherwise reports warn that the PR branch is based on an older target.
Without Neo4j: `python -m pipeline.baseline full --no-neo4j` then `scripts/make_demo_branches.sh --reports files`.
Remove the demo branches yourself with `git branch -D <names>` when you no longer need them (they are unmerged, so `-d` refuses).

## Tests
`.venv/bin/python -m pytest tests` (needs the setup above and the .NET 10 SDK). The scanner tests run the real scanners on a temporary
git copy of `config/` + `samples/`. `tests/expected_edges.yml` is a **hand-written** list of expected edges for the synthetic-extended
sample; `tools/compare_expected.py` reports recall against it (synthetic data only).

## Layout
`samples/` logical repos - `scanners/` - `linker/` (cross-repo linking) - `graph/` (Neo4j compose, loader, Cypher queries) - `impact/` (traversal, trace CLI, PR impact engine and report) - `scripts/` (demo branches) -
`schema/` - `config/` (repo paths, route/naming conventions, graph store) - `docs/` - `tools/` - `pipeline/` - `tests/`.
Planned: CI simulation, `explorer-api/`, `explorer/`, `eval/`.
