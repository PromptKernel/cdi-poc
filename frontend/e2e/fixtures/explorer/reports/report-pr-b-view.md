# Impact report: pr-b-view → main

> **Synthetic data.** At least one changed file is synthetic (written for this PoC, not upstream sample code); objects marked *synthetic* below. Results on the synthetic sample say nothing about accuracy on real code.

## Run
- PR branch `pr-b-view` @ `1caa0c3a`; target `main` @ `096d5db9`; merge-base `096d5db9` (diff is merge-base..PR, three-dot)
- Baseline graph (Neo4j, read-only): commits {"web": "23f6a263", "api": "23f6a263", "db": "57e1a2ce"}, loaded 2026-11-11T10:01:00+00:00 (full)
- Graph before/after PR (in memory; the stored baseline is not modified): nodes/edges [115, 125] → [115, 125]
- Depth limits (config, placeholder): downstream 12, upstream 12
- **PR run duration 2.857 s** (overlay scan 2.733 s; rest = query, mapping, traversal) — measured on this small synthetic sample only
- Overlay scan plan: {"db": {"changed": ["synthetic/views/vwItemGroup.sql"], "deleted": [], "dependents_rescanned": ["synthetic/procedures/spGetItemsByGroup.sql"]}}

## Summary

| # | Changed object | Kind | Repo | Change | Risk (rule) | Consumers (screens / endpoints / methods / SQL) | Synthetic |
|---|---|---|---|---|---|---|---|
| 1 | `dbo.vwItemGroup` | SQL_VIEW | db | modified | Medium (`R5-inferred-path-to-screen`) | 1 / 1 / 4 / 1 | yes |

## Changed files

- `db:synthetic/views/vwItemGroup.sql` (M) synthetic — 1 node(s); hunks: old (4, 4) → new (4, 4)

## Graph delta (baseline → after PR)
- nodes added 0, removed 0; edges added 0, removed 0, moved (same link, different line) 0, changed (confidence/reason/attrs) 0

## Changed objects

### 1. `dbo.vwItemGroup`
- **Changed object:** `dbo.vwItemGroup` — **kind:** SQL_VIEW — **repo:** db — **change:** modified — **synthetic**
- **Evidence:** db:synthetic/views/vwItemGroup.sql:3–6; hunks (old/new): [[(4, 4), (4, 4)]]; matched on the new/old side
- **Risk:** **Medium** — rule `R5-inferred-path-to-screen`: a UI screen depends on this object, but the path includes at least one inferred link (matched: inferred_path_reaches_ui = True)
- **Required developer action:** Review the consumers below (the inferred link is named in each path) and run the selected tests.
- **Potential consumers:** screens: `GroupReportComponent` [INFE]; UI services: `GroupReportService.getItemsIn` [INFE]; API endpoints: `ShopApp.Synthetic.Controllers.GroupController.ItemsIn(string)` [INFE]; business/data-access methods: 4; SQL objects: `dbo.spGetItemsByGroup` [CONF]
- **Confidence:** mapping of hunks to this node: from scanner locations; consumer paths: 4 confirmed, 4 inferred; unresolved links on/under it: 0 own, 0 introduced by this PR

## A. CONFIRMED paths
Every hop is a confirmed static link (resolved symbol, literal-matched route or name, table reference in DDL).
Reading a hop: `A → B` means A depends on B (the stored edge direction). A path starts at the changed object and walks outward through its consumers or dependencies.

### `dbo.vwItemGroup` (modified)
**Consumers — who depends on it (4):**
- DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` — found in the baseline graph
    - `READS_VIEW` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetItemsByGroup` → SQL_VIEW `dbo.vwItemGroup` — db:synthetic/procedures/spGetItemsByGroup.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetItemsByGroup` → SQL_PROC `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `linker:sql-name-match` @23f6a263 (synthetic)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` → SQL_REF `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
- DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.SqlPatternsDataAccess.CommandTextAssignment()` — found in the baseline graph
    - `READS_VIEW` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetItemsByGroup` → SQL_VIEW `dbo.vwItemGroup` — db:synthetic/procedures/spGetItemsByGroup.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetItemsByGroup` → SQL_PROC `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `linker:sql-name-match` @23f6a263 (synthetic)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.SqlPatternsDataAccess.CommandTextAssignment()` → SQL_REF `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/SqlPatternsDataAccess.cs:58 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
- SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` — found in the baseline graph
    - `READS_VIEW` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetItemsByGroup` → SQL_VIEW `dbo.vwItemGroup` — db:synthetic/procedures/spGetItemsByGroup.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetItemsByGroup` → SQL_PROC `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `linker:sql-name-match` @23f6a263 (synthetic)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` → SQL_REF `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` — api:Synthetic/Services/GroupReportService.cs:35 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
- SQL_PROC `dbo.spGetItemsByGroup` — found in the baseline graph
    - `READS_VIEW` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetItemsByGroup` → SQL_VIEW `dbo.vwItemGroup` — db:synthetic/procedures/spGetItemsByGroup.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
**Dependencies — what it depends on (2; first 2 shown):**
- SQL_TABLE `dbo.tblGroup`
    - `READS_TABLE` [CONFIRMED_STATIC] SQL_VIEW `dbo.vwItemGroup` → SQL_TABLE `dbo.tblGroup` — db:synthetic/views/vwItemGroup.sql:6 via `scriptdom:table-reference` @1caa0c3a (synthetic)
- SQL_TABLE `dbo.tblItem`
    - `READS_TABLE` [CONFIRMED_STATIC] SQL_VIEW `dbo.vwItemGroup` → SQL_TABLE `dbo.tblItem` — db:synthetic/views/vwItemGroup.sql:5 via `scriptdom:table-reference` @1caa0c3a (synthetic)

## B. INFERRED paths
At least one hop is inferred (for example interface dispatch decided by runtime dependency injection). The inferred hop is flagged in each path.
Reading a hop: `A → B` means A depends on B (the stored edge direction). A path starts at the changed object and walks outward through its consumers or dependencies.

### `dbo.vwItemGroup` (modified)
**Consumers — who depends on it (4):**
- UI_COMPONENT `GroupReportComponent` — found in the baseline graph
    - `READS_VIEW` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetItemsByGroup` → SQL_VIEW `dbo.vwItemGroup` — db:synthetic/procedures/spGetItemsByGroup.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetItemsByGroup` → SQL_PROC `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `linker:sql-name-match` @23f6a263 (synthetic)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` → SQL_REF `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` — api:Synthetic/Services/GroupReportService.cs:35 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - `DISPATCHES_TO` [INFERRED] INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetItemNames(string)` → SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` — api:Synthetic/Services/GroupReportService.cs:33 via `roslyn:interface-implementation+di-registration` @23f6a263 (synthetic) — reason: interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at Startup.cs:28)
    - `CALLS` [CONFIRMED_STATIC] API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.ItemsIn(string)` → INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetItemNames(string)` — api:Synthetic/Controllers/GroupController.cs:29 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - `ROUTES_TO` [CONFIRMED_STATIC] HTTP_REQUEST `GET api/Group/Items/{}` → API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.ItemsIn(string)` — web:src/synthetic/group-report.service.ts:21 via `linker:route-match` @23f6a263 (synthetic)
    - `MAKES_REQUEST` [CONFIRMED_STATIC] UI_SERVICE_METHOD `GroupReportService.getItemsIn` → HTTP_REQUEST `GET api/Group/Items/{}` — web:src/synthetic/group-report.service.ts:21 via `tsmorph:http-url-fold` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] UI_COMPONENT `GroupReportComponent` → UI_SERVICE_METHOD `GroupReportService.getItemsIn` — web:src/synthetic/group-report/group-report.component.ts:22 via `tsmorph:type-resolved-call` @23f6a263 (synthetic)
- API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.ItemsIn(string)` — found in the baseline graph
    - `READS_VIEW` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetItemsByGroup` → SQL_VIEW `dbo.vwItemGroup` — db:synthetic/procedures/spGetItemsByGroup.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetItemsByGroup` → SQL_PROC `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `linker:sql-name-match` @23f6a263 (synthetic)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` → SQL_REF `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` — api:Synthetic/Services/GroupReportService.cs:35 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - `DISPATCHES_TO` [INFERRED] INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetItemNames(string)` → SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` — api:Synthetic/Services/GroupReportService.cs:33 via `roslyn:interface-implementation+di-registration` @23f6a263 (synthetic) — reason: interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at Startup.cs:28)
    - `CALLS` [CONFIRMED_STATIC] API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.ItemsIn(string)` → INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetItemNames(string)` — api:Synthetic/Controllers/GroupController.cs:29 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
- INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetItemNames(string)` — found in the baseline graph
    - `READS_VIEW` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetItemsByGroup` → SQL_VIEW `dbo.vwItemGroup` — db:synthetic/procedures/spGetItemsByGroup.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetItemsByGroup` → SQL_PROC `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `linker:sql-name-match` @23f6a263 (synthetic)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` → SQL_REF `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` — api:Synthetic/Services/GroupReportService.cs:35 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - `DISPATCHES_TO` [INFERRED] INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetItemNames(string)` → SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` — api:Synthetic/Services/GroupReportService.cs:33 via `roslyn:interface-implementation+di-registration` @23f6a263 (synthetic) — reason: interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at Startup.cs:28)
- UI_SERVICE_METHOD `GroupReportService.getItemsIn` — found in the baseline graph
    - `READS_VIEW` [CONFIRMED_STATIC] SQL_PROC `dbo.spGetItemsByGroup` → SQL_VIEW `dbo.vwItemGroup` — db:synthetic/procedures/spGetItemsByGroup.sql:7 via `scriptdom:table-reference` @57e1a2ce (synthetic)
    - `RESOLVES_TO` [CONFIRMED_STATIC] SQL_REF `dbo.spGetItemsByGroup` → SQL_PROC `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `linker:sql-name-match` @23f6a263 (synthetic)
    - `CALLS_PROCEDURE` [CONFIRMED_STATIC] DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` → SQL_REF `dbo.spGetItemsByGroup` — api:Synthetic/DataAccess/GroupDataAccess.cs:46 via `roslyn:sqlcommand-storedprocedure` @23f6a263 (synthetic)
    - `CALLS` [CONFIRMED_STATIC] SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` → DATA_ACCESS_METHOD `ShopApp.Synthetic.DataAccess.GroupDataAccess.ReadItemsByGroup(string)` — api:Synthetic/Services/GroupReportService.cs:35 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - `DISPATCHES_TO` [INFERRED] INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetItemNames(string)` → SERVICE_METHOD `ShopApp.Synthetic.Services.GroupReportService.GetItemNames(string)` — api:Synthetic/Services/GroupReportService.cs:33 via `roslyn:interface-implementation+di-registration` @23f6a263 (synthetic) — reason: interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at Startup.cs:28)
    - `CALLS` [CONFIRMED_STATIC] API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.ItemsIn(string)` → INTERFACE_METHOD `ShopApp.Synthetic.Services.IGroupReportService.GetItemNames(string)` — api:Synthetic/Controllers/GroupController.cs:29 via `roslyn:semantic-invocation` @23f6a263 (synthetic)
    - `ROUTES_TO` [CONFIRMED_STATIC] HTTP_REQUEST `GET api/Group/Items/{}` → API_ENDPOINT `ShopApp.Synthetic.Controllers.GroupController.ItemsIn(string)` — web:src/synthetic/group-report.service.ts:21 via `linker:route-match` @23f6a263 (synthetic)
    - `MAKES_REQUEST` [CONFIRMED_STATIC] UI_SERVICE_METHOD `GroupReportService.getItemsIn` → HTTP_REQUEST `GET api/Group/Items/{}` — web:src/synthetic/group-report.service.ts:21 via `tsmorph:http-url-fold` @23f6a263 (synthetic)

## C. UNRESOLVED / not found
Nothing below is a confirmed or inferred path. These are places where the graph is incomplete or a reference does not resolve.

### C1. Introduced by this PR (present after the PR, absent in the baseline)
_None._

### C2. Pre-existing unresolved links on or under the changed objects (already present in the baseline)
_None._

### C3. Context: unresolved requests that might consume a changed endpoint (not linked; not claimed as consumers)
- GroupReportService.getHeadcount — web:src/synthetic/group-report.service.ts:17 — reason: URL part comes from runtime configuration (this._config.get('reportsRoute')); not statically resolvable; screen(s) that call it: GroupReportComponent
- GroupReportService.exportReport — web:src/synthetic/group-report.service.ts:26 — reason: URL is entirely a runtime value (url); no static path to match

## Tests to run
Ranked: (1) explicit `@covers` annotation (CONFIRMED), (2) a test that statically references an affected object (CONFIRMED), (3) naming/file-convention mappings (INFERRED).

**1. Annotation-based (CONFIRMED)**
- `GroupReportComponent > is declared` — web:src/synthetic/group-report.service.spec.ts:24; mapped by: annotation, convention; for changed object(s): dbo.vwItemGroup; path confidence INFERRED
    - `TESTS` [INFERRED] TEST `GroupReportComponent > is declared` → UI_SERVICE_METHOD `GroupReportService.getItemsIn` — web:src/synthetic/group-report.service.spec.ts:24 via `naming-convention` @23f6a263 (synthetic) — reason: mapped by naming convention (not by symbol reference or annotation)

**2. Static reference from the test (CONFIRMED)**
_None._

**3. Naming / file-convention (INFERRED) — grouped separately: a spec file maps to every method of the same-named source file, so this list fans out and over-selects.** (2 tests)
- `GroupReportService > archive posts to the Group API` — web:src/synthetic/group-report.service.spec.ts:16; via GroupReportService.getItemsIn (naming-convention)
- `GroupReportService > should be created` — web:src/synthetic/group-report.service.spec.ts:10; via GroupReportService.getItemsIn (naming-convention)

---
Risk labels come only from `config/risk-rules.yml` (first matching rule; no catch-all). An object with no matching rule has no label. The default critical list is a placeholder.
