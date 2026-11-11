# cdi-poc: a cross-layer dependency graph and PR impact PoC

## Purpose
Static scanners extract evidence-backed dependencies across a frontend, a .NET API and SQL Server code. A shared graph schema
carries them; later milestones link them across repos, load a graph store, and report which workflows a code change may affect.

## Layout
- `samples/web|api|db` - the three logical repos (folders of this one git repo). `samples/*/LICENSE` is the upstream MIT licence; see `NOTICE`.
- `scanners/` - Roslyn (C#), ts-morph (TypeScript), ScriptDom (SQL); `scanners/common-dotnet` is shared.
- `schema/`, `config/`, `docs/`, `tools/`, `pipeline/`.
- Planned: `linker/`, `graph/`, `impact/`, `explorer-api/`, `explorer/`, `eval/`, `tests/`.

## Working rules
- Every claim in a report must trace to a stored edge with file:line, method, confidence and commit.
- Never promote an INFERRED or UNRESOLVED edge to CONFIRMED_STATIC.
- Keep paths, route patterns, naming conventions and rule thresholds in `config/`; nothing hardcoded to the samples.
- Anything that is not upstream sample code is labelled synthetic. Do not present synthetic results as real-world accuracy.
- Scanners refuse to run on a dirty git working tree (commit first).
- No cloud calls: CI and AI integrations are local stubs.
- `private/` and `docs/source/` are git-ignored; never commit them.

## Safety rules (always)
- Never delete files or folders without first listing exactly what will be removed and getting the owner's approval.
- Never run `rm -rf` (or any recursive delete) outside this repository.
- Never push without first showing the pre-push check output (private-name file grep, name search, gitleaks, author check) to the owner.

## Commands
- Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`; `(cd scanners/ts-morph && npm ci)`; .NET 10 SDK required.
- Scan: `pipeline/scan_all.sh` -> `out/graph/<repo>.json`.
