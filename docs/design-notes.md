# Design notes

Pipeline: scanners -> shared graph schema -> linker (cross-repo edges) -> graph store -> impact engine -> report.

* **Scanners** are static and need no running services: Roslyn (C#), ts-morph (TypeScript/Angular), Microsoft ScriptDom (T-SQL).
* **Layers** modelled: UI component/service, HTTP request, API endpoint, business-service method, data-access method,
  SQL procedure/view/table. Layer classification of C# classes is configurable (`config/naming.yml`).
* **Evidence first**: every edge carries file, location, method, confidence and commit. Uncertain links are labelled, never promoted.
* **Configurable**: repo paths (`config/repos.yml`), route and HTTP-client conventions (`config/routes.yml`), naming and test
  conventions (`config/naming.yml`). Risk labels, when added, come from a rule file with neutral placeholder defaults.
* **Test mapping**: naming convention plus explicit `@covers` annotations; the method is recorded on each TESTS edge.
* **Deferred**: column-level impact (`SQL_COLUMN` is reserved in the schema); table-level comes first.
* **Simulation**: no cloud services are called. A CI wrapper, when added, is a thin shell around the local runner.
* **Linker** (`linker/`): route matching (verb + template), SQL reference -> definition by name, test -> node by annotation or convention.
  Exact unique matches are CONFIRMED_STATIC, ambiguous or heuristic ones INFERRED, everything else an UNRESOLVED edge with a reason.
* **Graph store**: Neo4j Community in Docker (`graph/`); nodes carry the `:Node` label plus a kind label, relationships use the edge type and keep
  every edge field as properties. Loading is idempotent (MERGE by id).
* **Trace**: `impact/traverse.py` (in-memory) and `graph/neo4j_query.py` (Cypher) return the same maximal paths; tests assert they are identical.
  A path's confidence is its weakest hop.
* **Baseline and PR runs**: the baseline runner writes the graph (full replace, or incremental sync plus a whole-graph re-link). The impact engine reads it read-only,
  overlays the PR's changed files in memory, re-links, and reports what the PR changes. Details in `docs/impact-report.md`.
