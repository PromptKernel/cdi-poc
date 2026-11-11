<!-- cdi-poc:impact-report:v1 pr=pr-f-route -->
## Dependency impact (advisory)

**Advisory:** this comment is informational only and does not block the merge (mode: advisory).
**Basis:** PR commit `cd485ba4` (`pr-f-route`) compared with target `main` @ `e53930cf` (merge-base `083771f6`); baseline graph commits: api `23f6a263`, db `57e1a2ce`, web `23f6a263`; baseline loaded 2026-11-11T10:25:29+00:00 (full).
Results are static-analysis evidence on this repository's own graph; confirmed and inferred links are kept separate.

### ⚠ Warnings
- The PR branch is based on an OLDER target: merge-base is 083771f6, the target tip is e53930cf. The diff covers only the PR's own changes (three-dot), but the baseline graph reflects the target tip.

### Changed objects (1)
| Object | Kind | Change | Risk (rule that fired) |
|---|---|---|---|
| `ShopApp.Controllers.ItemController.Index()` | API_ENDPOINT | modified | High (`R3-introduces-unresolved`) |
`ItemController.Index()` declared attributes changed: `route_template` `api/Item/Index` → `api/Item/List`

### Confirmed consumers (every hop a confirmed static link)
**`ShopApp.Controllers.ItemController.Index()`** (2):
- UI_COMPONENT `FetchItemComponent` — `web:src/app/fetch-item/fetch-item.component.ts:19` ⚠ broken by this PR
- UI_SERVICE_METHOD `ItemService.getItems` — `web:src/app/services/item.service.ts:26` ⚠ broken by this PR

### Tests to run — confirmed (explicit `@covers` annotation first, then direct static references)
_None._

### Unresolved / not found
Introduced by this PR (1):
- `ROUTES_TO` HTTP_REQUEST `GET api/Item/Index` — `web:src/app/services/item.service.ts:26` via `linker:route-match` @23f6a263: no API endpoint with verb GET and a route matching 'api/Item/Index' in the scanned repos; above it: `FetchItemComponent`

### Lower confidence
**Inferred consumers (0)** — at least one hop is inferred (for example DI-decided dispatch); listed in the full report with the inferred hop flagged.
**Naming/file-convention tests (2)** — INFERRED; a spec file maps to every method of its source file, so this list over-selects.
- `ItemService > should be created`
- `FetchItemComponent > should create`

_Full report: `out/report-pr-f-route.md` and `.json`. PR run 2.98 s (synthetic-scale repository)._
