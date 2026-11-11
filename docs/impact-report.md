# Impact analysis and report

`python -m cdi.impact.cli --target main --pr <branch> [--name <label>]` compares a PR branch with the target branch and writes
`out/report-<name>.md` and `out/report-<name>.json`. The baseline graph is read from Neo4j in a **read-only session** (or from `out/graph` with
`--store json`); a PR run never writes to it.

## Steps
1. `git diff --no-renames` between the **merge-base** and the PR head (three-dot), per logical repo folder: added / modified / deleted files and hunks.
2. Freshness check: the commit ids recorded in the baseline are compared with the target branch's folder commits, and the merge-base with the target tip.
   A stale baseline or an older merge-base puts a warning at the top of the report.
3. Overlay scan of the PR revision (in a git worktree at a named path, removed with `git worktree remove`): only changed files, plus files whose edges
   depend on changed definitions (for example the SQL test that executes a deleted procedure). The result is merged into an in-memory copy of the baseline and
   the whole graph is re-linked, so route matches, SQL resolution and test mappings reflect the PR.
4. Hunks to nodes: **old-side** ranges against baseline node locations, **new-side** ranges against overlay node locations. Pure deletions map on the old side.
   A scanned file whose changed lines touch no node is reported as `no graph node`; a file no scanner covers is `not scanned`.
5. For each changed object: consumers (reverse traversal, "who depends on it"), dependencies (forward traversal), tests, unresolved links.
   Depth limits come from `config/graph.yml` (`impact:`); if a traversal stops at the limit the report says so.
   Consumers of a modified or removed object come from the baseline (who depended on it before) and are marked "no longer holds after this PR" when a hop of
   the path no longer exists after the PR; consumers of an added object come from the after-PR graph.
6. Risk: the first matching rule in `config/risk-rules.yml`. **No rule, no label.** The rule id and why it matched are printed next to the label.

## Report sections
* Summary, changed files, graph delta (nodes/edges added, removed, moved, changed).
* Per changed object: changed object, kind, repo, change, potential consumers (screens, UI services, API endpoints, business/data-access methods, SQL objects), risk and rule,
  required developer action, evidence (file:line and hunks), confidence (counts of confirmed/inferred consumer paths and unresolved links).
* **A. CONFIRMED paths** - every hop is a confirmed static link. **B. INFERRED paths** - at least one hop is inferred (the hop is flagged).
  **C. UNRESOLVED / not found** - C1 introduced by the PR (for example a route that no longer matches, a procedure that is referenced but not defined, with the
  callers and screens above the broken reference), C2 pre-existing unresolved links on or under the changed objects, C3 unresolved requests that might be consumers of a
  changed endpoint (context only).
* Tests to run: (1) `@covers` annotation, (2) test that statically references an affected object, (3) naming/file convention, grouped separately because it fans out.
* Every path hop cites the stored edge: type, confidence, repo:file:line, analysis method, commit.

## Baseline runner
`python -m cdi.pipeline.baseline full` replaces the graph for the committed revision. `python -m cdi.pipeline.baseline incremental --from <rev> --to <rev>`
re-scans changed files (plus dependents), merges, re-links the whole graph and syncs Neo4j. Freshness (commit per logical repo, load time, mode) is stored
in a `Freshness` node. A full rebuild of the same commit gives identical node and edge ids (`backend/tests/test_baseline.py`).
