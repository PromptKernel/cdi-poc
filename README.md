# cdi-poc

> **Status: branch `restructure`, not merged to `main`.** As of 2026-11-11 the GitHub flow has run on github.com against the sample repository
> [`promptkernel/cdi-sample-app`](https://github.com/PromptKernel/cdi-sample-app) ([PR 1](https://github.com/PromptKernel/cdi-sample-app/pull/1), [PR 2](https://github.com/PromptKernel/cdi-sample-app/pull/2)):
> baseline cache, restore, one comment updated in place, and a commit status all worked. Fork PRs, GitHub's real error responses and larger repositories are **not verified** (docs/github-flow.md).

A cross-layer dependency graph and pull-request impact proof of concept. Static scanners read a frontend (TypeScript/Angular), an API (C#/.NET) and SQL Server code and emit one
shared, evidence-backed graph (every edge carries file:line, method, confidence and commit). A linker joins the layers, an impact engine maps a pull request's diff onto the graph, and the
result is a Markdown report, a PR comment and a commit status. The tool contains no knowledge of any particular application: a target repository describes itself in `.cdi/config.yml`.

### Real vs simulated
| Part | State |
|---|---|
| Scanners, linker, graph, impact engine, reports | **Real** code; evidence-backed; results on the synthetic sample say nothing about real-code accuracy |
| JSON baseline store (default), Neo4j store (optional) | **Real**, tested locally (Neo4j tests need a Neo4j you run yourself) |
| Read-only API (`cdi serve`) and the explorer's live mode | **Real**, tested locally (API tests; Playwright against a real `cdi serve`) |
| **GitHub flow** (comment upsert, commit status, baseline cache) | **Verified on real GitHub on 2026-11-11** for same-repository pull requests of the sample repository (see the two PRs above and docs/github-flow.md). **Not verified on GitHub:** fork PRs, real 403/404/422 responses, cache-miss / schema-mismatch / stale-baseline fallbacks, large repositories (fake-server tests only) |
| Azure DevOps adapter | **Written, never run** (disabled by default; shapes taken from public docs). Optional plugin, not the default flow |
| File-sink "simulated CI" (`out/pr-comment.md`) | **Simulation**: writes files only; used locally and as the no-token fallback |

## Layout
`backend/` (`src/cdi/` Python package, `scanners/` Roslyn, ts-morph and ScriptDom, `schema/`, `scripts/`, `tests/`) - `frontend/` (React + Cytoscape explorer) - `docs/` - `.github/` (composite action) -
`config.example/` (annotated config, GitHub workflows, optional Azure example). The sample application lives in its **own repository** (default name `promptkernel/cdi-sample-app`, a name only) and is
the target of demo pull requests; `backend/tests/fixtures/sample/` is a pinned copy used by the tests.

## Prerequisites
| Tool | Version | Why |
|---|---|---|
| Python | **3.10 or newer** (declared in `backend/pyproject.toml`; tested on 3.12 and 3.13) | the `cdi` package, API, tests |
| .NET SDK | **.NET 10** (the scanners target `net10.0`) | Roslyn (C#) and ScriptDom (SQL) scanners; the first build downloads NuGet packages |
| Node.js | **22.12 or newer** with npm (the frontend's Vite 8 needs 20.19+/22.12+, its Vitest 5 needs 22.12+/24+; developed on 24) | the TypeScript scanner and the explorer |
| git | any recent version (uses worktrees; tested on 2.50) | scanners record the commit of each repo folder |
| make | optional | convenience targets; every target has a plain-command equivalent below |

Neo4j is **optional** (see below). Docker is not used by this setup; `backend/Dockerfile` is an optional, unused way to package the CLI, and `backend/deploy/neo4j-compose.yml` is an optional convenience, neither is part of setup or tests.

## First-time setup
One command from the repository root:
```
make setup          # or: backend/scripts/setup.sh
```
It checks the prerequisites, then runs the plain commands:
```
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt          # pinned dependencies
.venv/bin/pip install -e backend                           # installs the `cdi` command into the venv
dotnet build backend/scanners/sql-scriptdom && dotnet build backend/scanners/dotnet-roslyn
(cd backend/scanners/ts-morph && npm ci)
(cd frontend && npm ci)
```
Then check it: `make test` (backend pytest + frontend typecheck and unit tests, no Neo4j), `make audit` (no sample-specific names in `backend/` or `frontend/`), and `make smoke` (everything below, end to end, on free ports).
Without make, use `.venv/bin/cdi ...` for every `cdi` command in this README, or `source .venv/bin/activate`.

## Running a baseline
A **target repository** is any git checkout with a `.cdi/config.yml` (start from `config.example/config.yml`; docs/configuration.md). Scanners refuse to run when a logical repo's folder has uncommitted changes, so commit first.
```
make baseline CDI_TARGET=/path/to/target          # = cd /path/to/target && cdi baseline full
```
This scans every logical repo, links them, and writes the baseline to `out/baseline.json` inside the target (a JSON file with a schema version and the commit id of every repo; docs/graph-store.md).
`cdi baseline incremental --from <rev> --to <rev>` updates it from a commit range. `cdi export` writes a static snapshot for the explorer (`out/explorer`).

## A pull-request run
```
make pr PR=<branch-or-sha> CDI_TARGET=/path/to/target      # = cd /path/to/target && cdi pr --pr <branch>
```
It compares the branch with `branches.base` (default `main`; `--target` overrides) using the baseline, then writes `out/report-<branch>.md/.json`, `out/pr-comment.md` and `out/pr-status.json`. Advisory: the exit code is 0 unless blocking is
enabled in config and a deterministic policy fails. Six synthetic demo scenarios for the sample live in its `.cdi/scenarios.yml`; `python -m cdi.eval.scenarios` creates them as local branches (never pushed).
On GitHub the same analysis runs from a workflow: docs/github-flow.md.

## Starting both terminals
```
# terminal 1: the read-only API for the target
make serve CDI_TARGET=/path/to/target          # = cd /path/to/target && cdi serve --host 127.0.0.1 --port 8000 --cors-origin http://127.0.0.1:5173

# terminal 2: the explorer
make web                                       # dev server with hot reload; add `make web-preview` for a production build instead
```
Open http://127.0.0.1:5173: the header says **data source: live API (...)** and the **Analyze** page shows the baseline's schema version, load time and commit of each repo. Without an API the explorer shows a static snapshot (`cdi export`, then `data source: snapshot`).

Ports, hosts and URLs come from environment variables (defaults in parentheses), never from the code:

| Variable | Used by | Meaning |
|---|---|---|
| `CDI_API_HOST` (127.0.0.1), `CDI_API_PORT` (8000) | `cdi serve`, `make web` | where the API listens / where the page finds it |
| `CDI_WEB_HOST` (127.0.0.1), `CDI_WEB_PORT` (5173 dev, 4173 preview) | frontend dev/preview server, `make serve` | where the page is served; its origin is the one origin the API allows |
| `CDI_API_BASE_URL` | frontend dev/preview server | answers `/config.json` with this API URL (set by `make web`). A deployed build edits its own `dist/config.json` (`{"apiBaseUrl": "http://..."}`) instead; the URL is read at run time, not built in |
| `CDI_CORS_ORIGINS` | `cdi serve` | comma-separated explicit origins allowed to call the API from a browser; **a wildcard is refused** |
| `CDI_API_TOKEN` (unset) | `cdi serve` | when set, every data route needs `Authorization: Bearer <token>`; the page asks for it. Required for any non-loopback host |
| `CDI_TARGET` (.), `VENV` (.venv), `PR` | Makefile | target repository, virtual environment, pull request |
| `CDI_CONFIG` | all `cdi` commands | config file (default `.cdi/config.yml`) |

Cross-origin is solved with that explicit allowed origin (`make serve` passes the origin of `make web`); there is no proxy and no wildcard. Details: docs/api.md.

Plain commands for the same: `cd frontend && CDI_API_BASE_URL=http://127.0.0.1:8000 npm run dev`, and `cdi serve --cors-origin http://127.0.0.1:5173` from the target.

## Neo4j (optional)
The default store is the JSON file; nothing here needs Neo4j. To use it, run a Neo4j 5 server however you like, then set `graph.store: neo4j` (or `--store neo4j`) and the connection under `graph.neo4j` in `.cdi/config.yml`;
the password is read from the environment variable named by `graph.neo4j.password_env` (default `NEO4J_PASSWORD`) and is never stored in a file. The Neo4j tests run only when `NEO4J_PASSWORD` is set and a server is reachable.

## More
- `docs/configuration.md` config, profiles, schema, hardcoding audit - `docs/graph-store.md` stores and schema versions - `docs/api.md` API and explorer - `docs/github-flow.md` GitHub flow, trust model, what is verified
- `docs/impact-report.md`, `docs/schema.md`, `docs/explorer.md`, `docs/evaluation.md` (harness; needs a ground-truth file written by you first), `docs/ci-simulation.md` (local file-sink and the unrun Azure adapter), `LIMITATIONS.md`

## Troubleshooting
| Symptom | Cause and fix |
|---|---|
| `Refusing to scan: ... has uncommitted changes` | the scanner records the folder's commit; commit or stash the target's changes (changes outside the logical repo's folder are ignored) |
| `make serve` / `make baseline`: "CDI_TARGET must point at a repository that has .cdi/config.yml" | pass `CDI_TARGET=/path/to/target`; create `.cdi/config.yml` from `config.example/config.yml` |
| `cdi: command not found` / `.venv/bin/cdi` missing | run `make setup`, or use `.venv/bin/cdi` |
| Port already in use (`Port 5173 is already in use`, or the API cannot bind) | another program holds it; pick others: `make serve CDI_API_PORT=8100` and `make web CDI_API_PORT=8100 CDI_WEB_PORT=5200` (keep both terminals' values equal) |
| Page shows "cannot reach the API ... --cors-origin" | the API did not allow the page's exact origin. The origin is `http://CDI_WEB_HOST:CDI_WEB_PORT`; use the same values in both terminals, or add it to `CDI_CORS_ORIGINS` |
| Page asks for "a bearer token" | the API was started with `CDI_API_TOKEN`; type that token (kept for the tab only) |
| API answers 503 `no baseline available` / `schema version ... rebuild` | run `make baseline` (the baseline is missing or was written by another version of the tool) |
| `cdi serve` refuses `--host 0.0.0.0` | a non-loopback bind needs a token: `export CDI_API_TOKEN=...` |
| `.NET 10 SDK is required` or `dotnet: command not found` | install the .NET 10 SDK; on Homebrew set `DOTNET_ROOT=/opt/homebrew/opt/dotnet/libexec` if it is not found (the tool tries that path itself) |
| First `dotnet build` is slow or fails offline | it restores NuGet packages from the network once |
| `npm ci` complains about the Node version | use Node 22.12 or newer |
| `make smoke` fails | it prints the failing check and still stops only its own processes and removes only its own `cdi-smoke-*` temporary directory (`--keep` keeps it) |
| Neo4j tests skipped | expected without `NEO4J_PASSWORD`; the suite is green without Neo4j |

## Licence
This repository has **no top-level licence file**; no licence is granted for it at this time. The sample application is derived from an MIT-licensed upstream project and is credited in its own repository and in `NOTICE`.
