# Configuration

A target repository describes itself in `.cdi/config.yml`. The tool contains no knowledge of any particular application: folders,
scanner selection, naming and routing conventions, risk rules, branches and limits all come from this file (plus a framework profile).

* Example: [`config.example/config.yml`](../config.example/config.yml). Schema: [`backend/schema/config.schema.json`](../backend/schema/config.schema.json) (`cdi config schema`).
* Validate: `cdi config validate [--file PATH]`. Show the fully resolved configuration: `cdi config show`.

## Precedence (low to high)
1. Tool defaults: `backend/src/cdi/config/profiles/_base.yml` (risk rules, limits, CI defaults; every value that is a guess of ours is marked *placeholder, unvalidated*).
2. Framework profile named by `profile:` (`cdi config profiles`): conventions only. Today: `aspnet-angular-sqlserver`.
3. The repository's `.cdi/config.yml`.
4. Environment overrides: `CDI__<section>__<key>=<YAML value>`, for example `CDI__ci__blocking__enabled=true`, `CDI__limits__max_depth_downstream=6`.
   `CDI_CONFIG` selects the config file. Dictionaries merge key by key; lists are replaced.

The merged result is validated. Unknown keys, a wrong type, an unknown profile or scanner plugin, duplicate repo names and a risk rule
with an undefined label are errors with the path of the offending key. Secrets are never stored: the file holds only the *name* of
the environment variable (`graph.neo4j.password_env`).

## Sections
| Section | Purpose |
|---|---|
| `repos[]` | logical repos: `name`, `path`, `scanner: {plugin, include[], exclude[]}` (globs choose the files a plugin reads) |
| `synthetic` | path segments / header marker that label demo-only files |
| `branches.base` | the branch the baseline is built from and PRs are compared with |
| `limits` | traversal depth, PR comment cap, maximum changed files (placeholders of ours) |
| `conventions` | `api`, `frontend`, `matching`, `layers`, `sql`, `sql_access`, `tests` (profile defaults; override per key) |
| `risk` | `labels`, `critical_objects`, `rules` (first match wins, no catch-all) |
| `graph` | `store: json \| neo4j`, Neo4j connection (password via `password_env`) |
| `impact`, `ci` | consumer kinds shown in reports; comment/status/blocking settings and the optional Azure adapter |

## Scanner plugins
`cdi.plugins` is the registry: `dotnet-roslyn` (C#), `ts-morph` (TypeScript), `sql-scriptdom` (T-SQL). A plugin declares its layer,
how to run it and default include/exclude globs; a new scanner registers itself there and nothing else needs to name it.
One plugin per logical repo for now (a repo that mixes languages is split into two logical repos).

## What moved out of the scanners
Each of these was a literal in scanner code and is now a key under `conventions` (set by the profile, overridable per repository):

| Was in | Now |
|---|---|
| Roslyn: constructed SQL command type | `sql_access.command_types` |
| Roslyn: command text / command type member names | `sql_access.command_text_member`, `sql_access.command_type_member` |
| Roslyn: value that marks a stored-procedure command | `sql_access.stored_procedure_markers` |
| ScriptDom: procedures whose EXEC means dynamic SQL | `sql.dynamic_exec_procedures` |
| ScriptDom: temp-table name prefix skipped | `sql.ignored_name_prefixes` |
| ts-morph: component decorator used for the selector | `frontend.component_decorators` (already a list, now used everywhere) |
| ts-morph: test case / suite call names | `frontend.test_functions` |
| Roslyn, ScriptDom, linker: default SQL schema (`dbo`) | `sql.default_schema` (no default in code) |
| the six scenario PR edits | `.cdi/scenarios.yml` in the target repository |

## How the scanners see it
The scanners are separate programs. `cdi.config.materialize` writes the resolved conventions (`repos.yml`, `routes.yml`, `naming.yml`, derived and not meant to be edited) to a **private
directory under the system temp directory** (one per process, mode 0700) and the scanners read those. The directory is removed when the run ends, on success, on failure and on SIGTERM through `cdi`
(it cannot be removed after `kill -9`). Only a directory this process created is ever removed: a real directory, a direct child of the temp directory, with the `cdi-scanner-config-` prefix, holding only the
three files we wrote, and not a symlink. Leftovers from versions before this change are not touched automatically.

### Wording about synthetic data
Reports, the PR comment, the export/API notice, the evaluation label and the explorer banner do not carry a fixed claim about any sample. They say "synthetic" only when the data contains files that
the repository's own `synthetic:` settings flagged (`path_segments`, `header_marker`); otherwise they say that the output is static-analysis evidence not validated against other code bases.

## Hardcoding audit
`cdi audit` (`backend/tools/audit_hardcoding.py`) fails when a sample-specific name appears in `backend/` or `frontend/` source. The vocabulary
is in `backend/tools/audit_terms.txt`; `backend/tests/` (the pinned fixture) is exempt. A line carrying `audit:allow(<reason>)` is skipped.
