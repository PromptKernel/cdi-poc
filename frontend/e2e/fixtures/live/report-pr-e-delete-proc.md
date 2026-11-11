# Impact report: pr-e-delete-proc → main

> **Synthetic data.** At least one changed file is synthetic (written for this PoC, not upstream sample code); objects marked *synthetic* below. Results on the synthetic sample say nothing about accuracy on real code.

## ⚠ Warnings
- The PR branch is based on an OLDER target: merge-base is 083771f6, the target tip is e53930cf. The diff covers only the PR's own changes (three-dot), but the baseline graph reflects the target tip.

## Run
- PR branch `pr-e-delete-proc` @ `773919c7`; target `main` @ `e53930cf`; merge-base `083771f6` (diff is merge-base..PR, three-dot)
- Baseline graph (Neo4j, read-only): commits {"web": "23f6a263", "api": "23f6a263", "db": "57e1a2ce"}, loaded 2026-11-11T10:25:29+00:00 (full)
- Graph before/after PR (in memory; the stored baseline is not modified): nodes/edges [115, 125] → [117, 124]
- Depth limits (config, placeholder): downstream 12, upstream 12
- **PR run duration 2.263 s** (overlay scan 2.156 s; rest = query, mapping, traversal) — measured on this small synthetic sample only
- Overlay scan plan: {"db": {"changed": [], "deleted": ["synthetic/procedures/spGetGroupHeadcount.sql"], "dependents_rescanned": ["synthetic/tests/test_spGetGroupHeadcount.sql"]}}

## Summary

| # | Changed object | Kind | Repo | Change | Risk (rule) | Consumers (screens / endpoints / methods / SQL) | Synthetic |
|---|---|---|---|---|---|---|---|
| 1 | `dbo.spGetGroupHeadcount` | SQL_PROC | db | removed | High (`R2-removed-with-consumers`) | 0 / 1 / 4 / 0 | yes |

## Changed files

- `db:synthetic/procedures/spGetGroupHeadcount.sql` (D) synthetic — 1 node(s); hunks: old (1, 10) → new None

## Graph delta (baseline → after PR)
- nodes added 3, removed 1; edges added 4, removed 5, moved (same link, different line) 0, changed (confidence/reason/attrs) 0
  - nodes_removed: `db:sql_proc:dbo.spGetGroupHeadcount`
  - nodes_added: `db:sql_ref:dbo.spGetGroupHeadcount`
  - nodes_added: `linker:unresolved:annotation_target_not_found:dbo.spGetGroupHeadcount`
  - nodes_added: `linker:unresolved:referenced_not_found:dbo.spGetGroupHeadcount`
  - edges_removed: `CALLS_PROCEDURE|db:test:synthetic/tests/test_spGetGroupHeadcount.sql::GroupTests.test spGetGroupHeadcount counts items per group|db:sql_proc:dbo.spGetGroupHeadcount|synthetic/tests/test_spGetGroupHeadcount.sql:7:5`
  - edges_removed: `READS_TABLE|db:sql_proc:dbo.spGetGroupHeadcount|db:sql_table:dbo.tblGroup|synthetic/procedures/spGetGroupHeadcount.sql:7:10`
  - edges_removed: `READS_TABLE|db:sql_proc:dbo.spGetGroupHeadcount|db:sql_table:dbo.tblItem|synthetic/procedures/spGetGroupHeadcount.sql:8:15`
  - edges_removed: `RESOLVES_TO|api:sql_ref:dbo.spGetGroupHeadcount|db:sql_proc:dbo.spGetGroupHeadcount|Synthetic/DataAccess/GroupDataAccess.cs:24:34`
  - edges_removed: `TESTS|db:test:synthetic/tests/test_spGetGroupHeadcount.sql::GroupTests.test spGetGroupHeadcount counts items per group|db:sql_proc:dbo.spGetGroupHeadcount|synthetic/tests/test_spGetGroupHeadcount.sql:4:0`
  - edges_added: `CALLS_PROCEDURE|db:test:synthetic/tests/test_spGetGroupHeadcount.sql::GroupTests.test spGetGroupHeadcount counts items per group|db:sql_ref:dbo.spGetGroupHeadcount|synthetic/tests/test_spGetGroupHeadcount.sql:7:5`
  - edges_added: `RESOLVES_TO|api:sql_ref:dbo.spGetGroupHeadcount|linker:unresolved:referenced_not_found:dbo.spGetGroupHeadcount|Synthetic/DataAccess/GroupDataAccess.cs:24:34`
  - edges_added: `RESOLVES_TO|db:sql_ref:dbo.spGetGroupHeadcount|linker:unresolved:referenced_not_found:dbo.spGetGroupHeadcount|synthetic/tests/test_spGetGroupHeadcount.sql:7:5`
  - edges_added: `TESTS|db:test:synthetic/tests/test_spGetGroupHeadcount.sql::GroupTests.test spGetGroupHeadcount counts items per group|linker:unresolved:annotation_target_not_found:dbo.spGetGroupHeadcount|synthetic/tests/test_spGetGroupHeadcount.sql:4:0`

## Changed objects

### 1. `dbo.spGetGroupHeadcount`
- **Changed object:** `dbo.spGetGroupHeadcount` — **kind:** SQL_PROC — **repo:** db — **change:** removed — **synthetic**
- **Evidence:** db:synthetic/procedures/spGetGroupHeadcount.sql:3–10; hunks (old/new): [[(1, 10), None]]; matched on the file side
- **Risk:** **High** — rule `R2-removed-with-consumers`: an object that other objects depend on is removed (matched: change = removed; has_consumers = True)
- **Required developer action:** Do not merge until every consumer listed below is updated or the removal is reverted; run the selected tests.
- **Potential consumers:** screens: none found; UI services: none found; API endpoints: `ShopApp.Synthetic.Controllers.GroupController.Headcount()` [INFE]; business/data-access methods: 4; SQL objects: none found
- **Confidence:** mapping of hunks to this node: from scanner locations; consumer paths: 3 confirmed, 2 inferred; unresolved links on/under it: 0 own, 3 introduced by this PR

## A. CONFIRMED paths
Every hop is a confirmed static link (resolved symbol, literal-matched route or name, table reference in DDL).
Reading a hop: `A → B` means A depends on B (the stored edge direction). A path starts at the changed object and walks outward through its consumers or dependencies.

### `dbo.spGetGroupHeadcount` (removed)
**Consumers — who depends on it (3):**
- **BROKEN BY THIS PR (held in the baseline, not after it)** — DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` — found in the baseline graph
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetGroupHeadcount` → SQL_PROC `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `linker:sql-name-match` @23f6a263 (synthetic)  ⚠ **no longer holds after this PR** (now `RESOLVES_TO` [UNRESOLVED] at api:Synthetic/DataAccess/GroupDataAccess.cs:24: referenced procedure 'dbo.spGetGroupHeadcount' is called/used but no definition was found in any scanned repo)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
- **BROKEN BY THIS PR (held in the baseline, not after it)** — DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.SqlPatternsDataAccess.ObjectInitializer()` — found in the baseline graph
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetGroupHeadcount` → SQL_PROC `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `linker:sql-name-match` @23f6a263 (synthetic)  ⚠ **no longer holds after this PR** (now `RESOLVES_TO` [UNRESOLVED] at api:Synthetic/DataAccess/GroupDataAccess.cs:24: referenced procedure 'dbo.spGetGroupHeadcount' is called/used but no definition was found in any scanned repo)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.SqlPatternsDataAccess.ObjectInitializer()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/SqlPatternsDataAccess.cs:42 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
- **BROKEN BY THIS PR (held in the baseline, not after it)** — SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` — found in the baseline graph
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetGroupHeadcount` → SQL_PROC `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `linker:sql-name-match` @23f6a263 (synthetic)  ⚠ **no longer holds after this PR** (now `RESOLVES_TO` [UNRESOLVED] at api:Synthetic/DataAccess/GroupDataAccess.cs:24: referenced procedure 'dbo.spGetGroupHeadcount' is called/used but no definition was found in any scanned repo)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` — api:Synthetic/Services/GroupReportService.cs:20 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
**Dependencies — what it depends on (2; first 2 shown):**
- SQL_TABLE `dbo.tblGroup`
    - `READS_TABLE` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetGroupHeadcount` → SQL_TABLE `dbo.tblGroup` — db:synthetic/procedures/spGetGroupHeadcount.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
- SQL_TABLE `dbo.tblItem`
    - `READS_TABLE` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetGroupHeadcount` → SQL_TABLE `dbo.tblItem` — db:synthetic/procedures/spGetGroupHeadcount.sql:8 via `scriptdom:table-reference` @57e1a2ce (synthetic)

## B. INFERRED paths
At least one hop is inferred (for example interface dispatch decided by runtime dependency injection). The inferred hop is flagged in each path.
Reading a hop: `A → B` means A depends on B (the stored edge direction). A path starts at the changed object and walks outward through its consumers or dependencies.

### `dbo.spGetGroupHeadcount` (removed)
**Consumers — who depends on it (2):**
- **BROKEN BY THIS PR (held in the baseline, not after it)** — API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.Headcount()` — found in the baseline graph
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetGroupHeadcount` → SQL_PROC `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `linker:sql-name-match` @23f6a263 (synthetic)  ⚠ **no longer holds after this PR** (now `RESOLVES_TO` [UNRESOLVED] at api:Synthetic/DataAccess/GroupDataAccess.cs:24: referenced procedure 'dbo.spGetGroupHeadcount' is called/used but no definition was found in any scanned repo)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` — api:Synthetic/Services/GroupReportService.cs:20 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - `DISPATCHES_TO` [INFERRED] INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetHeadcountReport()` → SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` — api:Synthetic/Services/GroupReportService.cs:18 via `roslyn:interface-implementation+di-registration` @23f6a263 (synthetic) — reason: interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at Startup.cs:28)
    - `CALLS` [CONFIRMED_STATIC] API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.Headcount()` → INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetHeadcountReport()` — api:Synthetic/Controllers/GroupController.cs:22 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
- **BROKEN BY THIS PR (held in the baseline, not after it)** — INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetHeadcountReport()` — found in the baseline graph
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetGroupHeadcount` → SQL_PROC `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `linker:sql-name-match` @23f6a263 (synthetic)  ⚠ **no longer holds after this PR** (now `RESOLVES_TO` [UNRESOLVED] at api:Synthetic/DataAccess/GroupDataAccess.cs:24: referenced procedure 'dbo.spGetGroupHeadcount' is called/used but no definition was found in any scanned repo)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` — api:Synthetic/Services/GroupReportService.cs:20 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - `DISPATCHES_TO` [INFERRED] INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetHeadcountReport()` → SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` — api:Synthetic/Services/GroupReportService.cs:18 via `roslyn:interface-implementation+di-registration` @23f6a263 (synthetic) — reason: interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at Startup.cs:28)

## C. UNRESOLVED / not found
Nothing below is a confirmed or inferred path. These are places where the graph is incomplete or a reference does not resolve.

### C1. Introduced by this PR (present after the PR, absent in the baseline)
- `CALLS_PROCEDURE` from TEST `GroupTests.test spGetGroupHeadcount counts items per group` — db:synthetic/tests/test_spGetGroupHeadcount.sql:7 via `scriptdom:exec-procedure` @773919c7 (synthetic)
  - reason: referenced procedure 'dbo.spGetGroupHeadcount' not defined in scanned repo 'db'
  - source: `EXEC dbo.spGetGroupHeadcount;`
  - no screen/endpoint/method above it was found through resolved links
- `RESOLVES_TO` from SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `linker:sql-name-match` @23f6a263 (synthetic)
  - reason: referenced procedure 'dbo.spGetGroupHeadcount' is called/used but no definition was found in any scanned repo
  - source: `SqlCommand cmd = new SqlCommand("spGetGroupHeadcount", con);`
  - referenced from: api:Synthetic/DataAccess/GroupDataAccess.cs:24, api:Synthetic/DataAccess/SqlPatternsDataAccess.cs:42
  - consumers above the broken reference (screens / endpoints / methods):
    - API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.Headcount()` [INFERRED] — Synthetic/Controllers/GroupController.cs:18
        - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
        - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` — api:Synthetic/Services/GroupReportService.cs:20 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
        - `DISPATCHES_TO` [INFERRED] INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetHeadcountReport()` → SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` — api:Synthetic/Services/GroupReportService.cs:18 via `roslyn:interface-implementation+di-registration` @23f6a263 (synthetic) — reason: interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at Startup.cs:28)
        - `CALLS` [CONFIRMED_STATIC] API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.Headcount()` → INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetHeadcountReport()` — api:Synthetic/Controllers/GroupController.cs:22 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` [CONFIRMED_STATIC] — Synthetic/DataAccess/GroupDataAccess.cs:19
        - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.SqlPatternsDataAccess.ObjectInitializer()` [CONFIRMED_STATIC] — Synthetic/DataAccess/SqlPatternsDataAccess.cs:38
        - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.SqlPatternsDataAccess.ObjectInitializer()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/SqlPatternsDataAccess.cs:42 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` [CONFIRMED_STATIC] — Synthetic/Services/GroupReportService.cs:18
        - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
        - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` — api:Synthetic/Services/GroupReportService.cs:20 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetHeadcountReport()` [INFERRED] — Synthetic/Services/IGroupReportService.cs:16
        - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetGroupHeadcount` — api:Synthetic/DataAccess/GroupDataAccess.cs:24 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
        - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadHeadcount()` — api:Synthetic/Services/GroupReportService.cs:20 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
        - `DISPATCHES_TO` [INFERRED] INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetHeadcountReport()` → SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetHeadcountReport()` — api:Synthetic/Services/GroupReportService.cs:18 via `roslyn:interface-implementation+di-registration` @23f6a263 (synthetic) — reason: interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at Startup.cs:28)
- `RESOLVES_TO` from SQL_REF `dbo.spGetGroupHeadcount` — db:synthetic/tests/test_spGetGroupHeadcount.sql:7 via `linker:sql-name-match` @773919c7 (synthetic)
  - reason: referenced procedure 'dbo.spGetGroupHeadcount' is called/used but no definition was found in any scanned repo
  - source: `EXEC dbo.spGetGroupHeadcount;`
  - referenced from: db:synthetic/tests/test_spGetGroupHeadcount.sql:7
  - no screen/endpoint/method above it was found through resolved links
- `TESTS` from TEST `GroupTests.test spGetGroupHeadcount counts items per group` — db:synthetic/tests/test_spGetGroupHeadcount.sql:4 via `annotation` @773919c7 (synthetic)
  - reason: @covers target 'dbo.spGetGroupHeadcount' matches no scanned node
  - no screen/endpoint/method above it was found through resolved links

### C2. Pre-existing unresolved links on or under the changed objects (already present in the baseline)
_None._

### C3. Context: unresolved requests that might consume a changed endpoint (not linked; not claimed as consumers)
- GroupReportService.getHeadcount — web:src/synthetic/group-report.service.ts:17 — reason: URL part comes from runtime configuration (this._config.get('reportsRoute')); not statically resolvable; screen(s) that call it: GroupReportComponent
- GroupReportService.exportReport — web:src/synthetic/group-report.service.ts:26 — reason: URL is entirely a runtime value (url); no static path to match

## Tests to run
Ranked: (1) explicit `@covers` annotation (CONFIRMED), (2) a test that statically references an affected object (CONFIRMED), (3) naming/file-convention mappings (INFERRED).

**1. Annotation-based (CONFIRMED)**
- `GroupTests.test spGetGroupHeadcount counts items per group` — db:synthetic/tests/test_spGetGroupHeadcount.sql:4; mapped by: annotation, static-reference; for changed object(s): dbo.spGetGroupHeadcount; path confidence CONFIRMED_STATIC; ⚠ the path to it is broken by this PR
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] TEST `GroupTests.test spGetGroupHeadcount counts items per group` → SQL_PROC `dbo.spGetGroupHeadcount` — db:synthetic/tests/test_spGetGroupHeadcount.sql:7 via `scriptdom:exec-procedure` @57e1a2ce (synthetic)  ⚠ **no longer holds after this PR** (now `CALLS_PROCEDURE` [UNRESOLVED] at db:synthetic/tests/test_spGetGroupHeadcount.sql:7: referenced procedure 'dbo.spGetGroupHeadcount' not defined in scanned repo 'db')

**2. Static reference from the test (CONFIRMED)**
_None._

**3. Naming / file-convention (INFERRED) — grouped separately: a spec file maps to every method of the same-named source file, so this list fans out and over-selects.** (1 tests)
- `Api.Tests.GroupTests.GroupController_Headcount_ReturnsRows()` — api:tests/Api.Tests/GroupTests.cs:21; via ShopApp.Synthetic.Controllers.GroupController.Headcount() (naming-convention)

---
Risk labels come only from `config/risk-rules.yml` (first matching rule; no catch-all). An object with no matching rule has no label. The default critical list is a placeholder.
