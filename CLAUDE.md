# cdi-poc: a cross-layer dependency graph and PR impact PoC

## Purpose
Static scanners extract evidence-backed dependencies across a frontend, a .NET API and SQL Server code. A shared graph schema
carries them; later milestones link them across repos, load a graph store, and report which workflows a code change may affect.

## Layout (branch `restructure`; see README)
- `backend/` - `src/cdi/` (linker, graph store, impact engine, CI comment/status/policy/adapters, pipeline, eval, export), `scanners/` (Roslyn C#, ts-morph TypeScript, ScriptDom SQL), `schema/`, `scripts/`, `tests/` (with `tests/fixtures/sample/`, a pinned copy of the sample).
- `frontend/` - the local React + Cytoscape graph explorer.
- `config.example/` - optional adapters and examples; `docs/` - documentation.
- `samples/` - the sample application, still here only until its own repository is approved and created (upstream MIT licence; see `NOTICE`).
- Configuration: the target repo's `.cdi/config.yml` (see `docs/configuration.md`); `cdi audit` enforces that `backend/` and `frontend/` name nothing from the sample.
- `cdi` commands: baseline, pr, export, serve (read-only API, `docs/api.md`), audit, config, github (`docs/github-flow.md`). The frontend reads its API URL from `config.json` at run time.

## Working rules
- Every claim in a report must trace to a stored edge with file:line, method, confidence and commit.
- Never promote an INFERRED or UNRESOLVED edge to CONFIRMED_STATIC.
- Keep paths, route patterns, naming conventions and rule thresholds in `.cdi/config.yml` (or a framework profile); nothing hardcoded to the samples. Run `cdi audit`.
- Anything that is not upstream sample code is labelled synthetic. Do not present synthetic results as real-world accuracy.
- Scanners refuse to run only when the logical repo's own folder has uncommitted changes (changes elsewhere in the git repo are ignored); commit first.
- No cloud calls: CI and AI integrations are local stubs; the Azure DevOps adapter is disabled by default and has never been run.
- `private/` and `docs/source/` are git-ignored; never commit them.

## Safety rules (always)
- Never delete files or folders without first listing exactly what will be removed and getting the owner's approval.
- Never run `rm -rf` (or any recursive delete) outside this repository.
- Never push without first showing the pre-push check output (private-name file grep, name search, gitleaks, author check) to the owner.

## Commands
- Setup: `python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt && .venv/bin/pip install -e backend --no-deps`; `(cd backend/scanners/ts-morph && npm ci)`; .NET 10 SDK required.
- Tests: `cd backend && ../.venv/bin/python -m pytest` (Neo4j tests skip without `NEO4J_PASSWORD`).
