# Limitations (what this PoC does not prove)

Status: milestone 3 (schema, scanners, linker, Neo4j load, trace, baseline runner, PR impact report). Items for later milestones are marked *(planned)*.

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
  until the next full rebuild; node and edge ids are checked for equality with a full rebuild only on the cases in `tests/test_baseline.py`.
* **Impact is computed on the target-tip baseline plus the PR overlay**, not on a real merge of the PR into the target; semantic conflicts and merge results are not modelled.
  Renames are treated as delete + add. Generated files, build-time code and non-scanned file types are reported as "not scanned".
* **Consumers of a changed object are the baseline's consumers**: dependents that exist only through UNRESOLVED links (dynamic SQL, config-built routes) cannot be listed;
  section C3 only lists unresolved requests as context.
* **Not built *(planned)*:** CI wrapper, explorer API and UI, evaluation harness.
* **No licence for the tooling.** The repository has no top-level licence file; only the upstream-derived sample is MIT.
