# Changes to the upstream sample, and additions

Upstream: https://github.com/AnkitSharma-007/CRUD.ASPCore.Angular.WebAPI.ADO @ 938cb17 (MIT, Copyright (c) 2021 Ankit).
Every change below is its own commit in this repository (`git log --oneline -- samples`).

## Verification of the upstream sample (before changes)
* Licence: MIT. `.sql` files: **none** (stored procedures and tables are referenced from C# but never defined).
* Build: the original `netcoreapp3.0` project with `Microsoft.AspNetCore.SpaServices.Extensions 3.0.0-preview6` was **not built**
  (3.0 is out of support; no matching SDK). Angular 8.1 / TypeScript 3.4 was not built either; the scanners read source only.

## Commit 1 - import (unchanged files)
Files are byte-identical to upstream, regrouped into three logical-repo folders:
`ClientApp/` -> `samples/web`, the ASP.NET project -> `samples/api`, `samples/db` (licence only). The MIT `LICENSE` is copied
into each folder. Upstream's root README is kept as `samples/api/README.upstream.md`.
Not imported: `ASPCoreWithAngular.sln` (project paths no longer match the split) and `.vs/.../db.lock` (IDE lock file).

## Later commits
| Change | Files | Why |
|---|---|---|
| Replace the upstream author's workstation name in the connection string with `localhost\SQLEXPRESS` (the original value remains visible in commit 1, which is the unchanged upstream import) | samples/api/appsettings.json | do not republish a personal machine name |
| `netcoreapp3.0` -> `net10.0`; SpaServices.Extensions `3.0.0-preview6...` -> `10.0.0`; System.Data.SqlClient `4.6.1` -> `4.9.0`; removed the npm `Exec` targets and `ClientApp` item groups | samples/api/ASPCoreWithAngular.csproj | .NET 10 is the supported LTS; frontend is now `samples/web`. `dotnet build` and the 2 synthetic tests pass on net10.0 |
| Synthetic SQL | samples/db/synthetic | the upstream ships no SQL |
| Synthetic API (controller, business service, data access, tests), DI registrations in `Startup.cs`, `tests/**` excluded from the main compile | samples/api/Synthetic, samples/api/tests, Startup.cs, csproj | exercise cross-layer edges |
| Synthetic web screen, service, spec, runtime config; route + declaration in `app.module.ts` | samples/web/src/synthetic, src/assets/config.json, src/app/app.module.ts | exercise a config-built route |

## Synthetic content (all labelled; `synthetic: true` in graph output)
| Item | Path |
|---|---|
| Reconstructed `tblEmployee`, `tblCities`, 5 procedures used by the sample's C# | samples/db/synthetic |
| 2nd table `tblDepartment`; view `vwEmployeeDepartment`; `spGetDepartmentHeadcount` (both tables); `spGetEmployeesByDepartment` (via the view) | samples/db/synthetic |
| The one synthetic dynamic-SQL string | `spSearchEmployees` (`sp_executesql` on a built string) |
| "Referenced, not found" | `DepartmentDataAccess.Archive` calls `spArchiveEmployee`, which is not defined in samples/db |
| Business-service layer, controller, data access | samples/api/Synthetic |
| API tests (naming convention and `@covers`), SQL test (`@covers`), TS spec (file convention) | samples/api/tests, samples/db/synthetic/tests, samples/web/src/synthetic |
| Config-built route | samples/web/src/synthetic/department-report.service.ts `getHeadcount()` |
| Non-synthetic dynamic SQL already in upstream | `EmployeeDataAccessLayer.GetEmployeeData` |
