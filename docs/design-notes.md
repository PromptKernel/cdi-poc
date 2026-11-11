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
