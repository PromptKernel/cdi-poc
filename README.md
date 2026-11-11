# cdi-poc

A cross-layer dependency graph and PR impact proof of concept: static scanners for a frontend (TypeScript/Angular), an API
(C#/.NET) and SQL Server code emit one shared, evidence-backed graph schema.

**Status: milestone 1 of the PoC (schema + three scanners).** Linker, graph load, impact engine, report, explorer and
evaluation are planned and not in this repository yet. See `LIMITATIONS.md`.

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
Requirements: git, Node 20+, Python 3.10+, .NET 10 SDK.
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
(cd scanners/ts-morph && npm ci)
```

## Run order (milestone 1)
1. Commit your working tree. Scanners **refuse to run on uncommitted changes**, so `commit_id` matches the scanned files.
2. `pipeline/scan_all.sh` - builds the .NET scanners, runs Roslyn/ts-morph/ScriptDom per logical repo, validates the output
   against `schema/graph.schema.json`. Output: `out/graph/{web,api,db}.json` (git-ignored).
3. `.venv/bin/python tools/show_workflow.py FetchEmployeeComponent spGetAllEmployees` - prints edges with the cited source line re-read from disk.

## Layout
`samples/` logical repos - `scanners/` - `schema/` - `config/` (repo paths, route and naming conventions) - `docs/` (`schema.md`, `design-notes.md`,
`changes.md`) - `tools/` - `pipeline/`. Planned: `linker/ graph/ impact/ explorer-api/ explorer/ eval/ tests/`.
