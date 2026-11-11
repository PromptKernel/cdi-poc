# Limitations (what this PoC does not prove)

Status: milestone 1 only (schema + scanners). Items for later milestones are marked *(planned)*.

* **Multiple repos are simulated with folders.** `samples/web|api|db` are folders of one git repository. Commit IDs come from
  `git log -1 -- <folder>`. The PoC does not test real multi-repo checkouts, per-repo branches, access control or cross-repo PR flows.
* **Synthetic data.** All SQL, the Department API/UI, the tests and any regression scenarios are synthetic and written by the
  tool author. Any metric measured on them says nothing about real code bases.
* **No runtime validation.** Nothing is executed: no SQL Server, no running API, no browser. Tests are scanned, not run
  (the SQL test and the Angular specs cannot run here; only the 2 synthetic xunit tests do).
* **Static-analysis blind spots.** Dynamic SQL, reflection, runtime DI, configuration-driven routes, message-based integrations
  and generated code cannot be fully resolved. They are labelled UNRESOLVED or INFERRED, never CONFIRMED.
* **Syntax-name matching.** The C# scanner has no ASP.NET/SqlClient references, so it recognises `SqlCommand`, route and verb
  attributes by name; a wrapper class with another name would be missed. The TS scanner recognises `HttpClient` by declared type name.
* **Inline SQL text** that is not a stored-procedure call is reported UNRESOLVED (not parsed).
* **Interface dispatch** is always INFERRED, so every path through an interface call has at least one INFERRED hop.
* **Column-level impact** is not implemented (`SQL_COLUMN` is reserved).
* **Sample build state:** the upstream Angular 8 frontend was not built; only the .NET 10 retarget builds and tests.
* **Not built *(planned)*:** linker, graph store load, impact engine, PR report, CI wrapper, explorer, evaluation harness.
* **No licence for the tooling.** The repository has no top-level licence file; only the upstream-derived sample is MIT.
