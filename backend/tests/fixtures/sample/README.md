# Test fixture: pinned copy of the sample (do not edit)

A small, pinned snapshot of the sample application used by the backend tests. Only files the scanners or the tests read are kept
(`.cs`, `.csproj`, `.sql`, `web/src/**/*.ts`, TypeScript config, a few small support files); templates, styles, lock files, icons and e2e files are left out.

* Source: the `samples/` folder of this repository at commit `f5c01806deaa81d4d8a3967a6bef7b8f8cad01d0` (66 of its 99 files).
* Upstream: derived from an MIT-licensed project; see `LICENSE` (per folder) and `NOTICE`. Synthetic additions are marked `SYNTHETIC` in their files.
* `config/` is the interim configuration for the fixture (it is replaced by a `.cdi/config.yml` in a later phase).
* Tests copy this directory into a temporary git repository, so scanner commit ids, dirty-tree checks and branch scenarios run on real git state.
* Sample-specific names (employees, departments, ...) are allowed here and in tests; they must not appear in backend/ or frontend/ source.
