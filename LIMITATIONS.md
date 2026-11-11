# Limitations (what this PoC does not prove)

Status: milestone 6 (schema, scanners, linker, Neo4j load, trace, baseline runner, PR impact report, simulated CI check, local explorer, evaluation harness). Items for later milestones are marked *(planned)*.

* **Multiple repos are simulated with folders.** `samples/web|api|db` are folders of one git repository. Commit IDs come from
  `git log -1 -- <folder>`. The PoC does not test real multi-repo checkouts, per-repo branches, access control or cross-repo PR flows.
* **Synthetic data.** All SQL, the Department API/UI, the tests and any regression scenarios are synthetic and written by the
  tool author. Any metric measured on them says nothing about real code bases.
* **No runtime validation.** Nothing is executed: no SQL Server, no running API, no browser. Tests are scanned, not run
  (the SQL test and the Angular specs cannot run here; only the 2 synthetic xunit tests do).
* **Runtime-decided behaviour is not resolved.** SQL text assembled at runtime, routes built from configuration values and interface calls whose
  implementation is chosen by dependency injection are reported as UNRESOLVED or INFERRED, never CONFIRMED. Reflection, event/message-based hand-offs and
  generated code are not modelled at all, so dependencies that run through them are absent from the graph.
* **Syntax-name matching.** The C# scanner has no ASP.NET/SqlClient references, so it recognises `SqlCommand`, route and verb
  attributes by name; a wrapper class with another name would be missed. The TS scanner recognises `HttpClient` by declared type name.
* **DI registrations are found only for `AddX<I, Impl>()` calls** (`AddTransient/AddScoped/AddSingleton` with two type arguments).
  Factory lambdas, `TryAdd*`, assembly scanning, keyed services and registrations built at runtime are not seen; an interface call
  is still reported as INFERRED dispatch to its implementing type, with a "no DI registration found" reason.
* **Types are matched by name because references are not loaded.** The C# scanner compiles source only (no ASP.NET or `SqlClient`
  references), so `SqlCommand`, route/verb attributes and test attributes are recognised by their written name, and the TS scanner
  recognises `HttpClient` by its declared type name. A renamed wrapper, an alias or a same-named unrelated type is mis-detected.
* **Overlay scans re-emit only edges evidenced in the changed files.** An edge evidenced in an unchanged file (for example an
  interface-to-implementation link when only the interface file changed) is taken from the baseline, not re-derived.
* **Inline SQL text** that is not a stored-procedure call is reported UNRESOLVED (not parsed).
* **Interface dispatch** is always INFERRED, so every path through an interface call has at least one INFERRED hop.
* **Column-level impact** is not implemented (`SQL_COLUMN` is reserved).
* **Sample build state:** the upstream Angular 8 frontend was not built; only the .NET 10 retarget builds and tests.
* **Route matching is template-based.** It handles literal segments, `{param}`/constraint segments, case, slashes and query strings.
  It does not model optional or catch-all parameters, areas, API versioning, route prefixes set elsewhere (`MapControllerRoute`, `UsePathBase`),
  conventional routing, or a gateway that rewrites paths. A request with a runtime-valued segment matching a literal route is only INFERRED.
* **SQL reference resolution is exact name matching** (case-insensitive, default schema applied). Synonyms, cross-database names, `USE`
  context, schema search paths and aliases are not modelled.
* **Test mapping by file or name convention fans out** (a spec file maps to every service method in the matching source file) and is
  therefore only INFERRED; only explicit `@covers` annotations are CONFIRMED. No coverage data is used.
* **Traversal skips UNRESOLVED links**, so anything reachable only through dynamic SQL, a config-built route or a missing definition is
  invisible to the trace (it is listed as an unresolved link at the node where the chain stops). This lowers recall by construction.
* **Neo4j is a local single Community instance** with no authentication beyond a local password and no persistence guarantees beyond a Docker volume.
* **Impact results on the synthetic sample say nothing about accuracy on real code.** The six demo scenarios, the sample, the risk rules and the depth limits are
  written by the tool author; the timings are from a very small repository. No false-positive or false-negative rate on real changes has been measured.
* **Risk labels are rule outputs, not predictions.** The rules in `config/risk-rules.yml` are unvalidated defaults and the critical list is a placeholder.
* **Incremental updates re-scan changed files plus files that depend on changed definitions**, not a full transitive closure. Cross-file facts that a scanner reads
  from elsewhere (for example the DI registration text shown in an inferred dispatch reason, or a base class changed in another file) can leave a stale `reason` or attribute
  until the next full rebuild; node and edge ids are checked for equality with a full rebuild only on the cases in `backend/tests/test_baseline.py`.
* **Impact is computed on the target-tip baseline plus the PR overlay**, not on a real merge of the PR into the target; semantic conflicts and merge results are not modelled.
  Renames are treated as delete + add. Generated files, build-time code and non-scanned file types are reported as "not scanned".
* **Consumers of a changed object are the baseline's consumers**: dependents that exist only through UNRESOLVED links (dynamic SQL, config-built routes) cannot be listed;
  section C3 only lists unresolved requests as context.
* **The CI check is a simulation.** No Azure DevOps service, pipeline run or token was used. The comment, thread and status shapes follow the public REST docs (api-version 7.1,
  URLs in `docs/ci-simulation.md`) and were **not tested against a real service**; the examples in those docs use integer enum values while we send the documented names; the authentication
  header, how the marker renders and whether the `cdiPocMarker` thread property is accepted are unverified. `config.example/optional/azure/azure-pipelines.yml` and the Azure DevOps adapter were never executed
  (the adapter's thread-finding and update logic is tested only against an in-memory fake).
* **No comment length limit is documented** on the pages consulted; the 20,000-character comment cap and 300-character status description cap are our own placeholders, unvalidated.
  A real service may enforce a different limit, and may not render everything we send.
* **Blocking policies can fire on intended changes** (a deliberate rename, deletion or route change whose callers are fixed in another PR). Blocking is off by default; it never uses a risk label.
* **PR-run timing** (about 2 to 5 s) is measured on a tiny synthetic repository on one machine; it says nothing about large repositories or CI agents.
* **The explorer shows structure only.** It draws stored edges and their evidence; it does not run code, measure behaviour, or judge correctness, and its data is the **synthetic-extended
  sample**, so it says nothing about real code bases. It is a static snapshot (`backend/src/cdi/export.py`), not a live view: re-export after rebuilding the baseline. It is read-only, local and
  unauthenticated (bound to 127.0.0.1 by default) and not hardened for hosting. "View on GitHub" links use the edge's commit id and only resolve if that commit exists in the configured repository.
  Layouts are automatic and large expansions become hard to read; filters and depth are the tools for that. Accessibility was considered (text list of visible nodes, line style plus colour,
  focus outlines) but not audited. The Playwright smoke test covers one end-to-end path in one browser (Chromium); it is not a full UI test suite.
* **The evaluation measures behaviour on synthetic data only.** Scenarios and ground truth are written by the tool's author on a tiny sample, so recall and false-positive numbers show consistency with
  those expectations, not detection of real defects; they are not evidence of accuracy on real code. The ground truth is written before the run and never edited to fit output, but the author of
  the ground truth is also the author of the tool, so it is not independent. "Workflow" means a screen or an API endpoint (configurable); another definition gives other numbers.
  Real regression history, critical-workflow test coverage and freshness over time cannot be measured here.
* **Not built:** an optional read-only API for the explorer (live from Neo4j).
* **No licence for the tooling.** The repository has no top-level licence file; only the upstream-derived sample is MIT.
