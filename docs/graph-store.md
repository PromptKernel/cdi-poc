# Baseline graph store

The impact engine compares a pull request with a **baseline**: the linked graph of the base branch plus a freshness record. Stores sit
behind one interface, `cdi.store.GraphStore`:

| Method | Meaning |
|---|---|
| `read()` | `(graph, freshness)`; raises `BaselineMissing` or `BaselineSchemaMismatch`. Never writes. |
| `write_full(graph, freshness)` | replace everything (full build) |
| `sync(graph, freshness)` | make the store equal to `graph` (incremental update); reports nodes/edges deleted |
| `snapshot()` | node and edge ids, used to prove a PR run did not change the baseline |

## Stores
* **JSON (default).** One file, `out/baseline.json` (`graph.json.path`), written atomically (temp file + rename), so a reader sees the old or the new
  file, never a partial one. No server, no driver. Layout: `schema_version`, `freshness`, `nodes[]`, `edges[]` (sorted by id, diff-friendly).
* **Neo4j (optional).** `graph.store: neo4j` or `--store neo4j`; the `neo4j` driver is imported only then. PR runs use a read-only session.
  The password is read from the variable named by `graph.neo4j.password_env`.

Select with `graph.store` in `.cdi/config.yml`, `CDI__graph__store=neo4j`, or `--store json|neo4j` (and `--store-path FILE` for the JSON file) on
`cdi.pipeline.baseline`, `cdi.pipeline.run_pr`, `cdi.impact.cli`, `cdi.impact.trace` and `cdi.export`.

## Freshness record
`schema_version`, `commits` (the commit id of **every logical repo** the baseline was built from), `loaded_at`, `mode` (`full` | `incremental`),
`from_commit`/`to_commit`, `counts`. The PR run compares these commits with the target branch and warns when the baseline is older.

## Schema version
`cdi.store.SCHEMA_VERSION` (currently 1) is written with every baseline. A different or missing version is **rejected** (`BaselineSchemaMismatch`): a
PR run reports state `notApplicable` with a comment telling the maintainer to rebuild, and the baseline command rebuilds with `full`. Bump the number
whenever the stored graph or freshness layout changes incompatibly.

## Other defaults wired in this phase
* `branches.base` is the **default** for `--target`; an explicit `--target` (or the PR's base ref passed by CI) overrides it.
* `limits.max_changed_files`: a PR that changes more files is not analysed. The comment says so (`PR too large, analysis skipped`, with the count and
  the limit) and the status is `notApplicable`; the run is still advisory (exit 0). The limit is a placeholder of ours.
