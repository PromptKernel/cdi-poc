# Shared graph schema (v1.0)

All three scanners, the linker and the impact engine use this one format. Machine-readable form:
`schema/graph.schema.json` (JSON Schema 2020-12). Each scanner writes one *fragment* per logical repo
(`out/graph/<repo>.json`); the linker adds cross-repo edges in `out/graph/linked.json`.

## Required edge fields

| Meaning | Field | Notes |
|---|---|---|
| source file | `source_file` | path, relative to the logical repo's folder, of the file that evidences the relationship |
| location | `location.{line,column,end_line,end_column}` | 1-based; `line` is mandatory |
| analysis method | `analysis_method` | `<tool>:<technique>`, e.g. `roslyn:semantic-invocation` |
| confidence | `confidence` | `CONFIRMED_STATIC` \| `INFERRED` \| `UNRESOLVED` (categorical on purpose: no invented numeric scores) |
| commit ID | `commit_id` (+ `repo`) | see "Commit IDs" below |
| relationship type | `type` | enum in the schema (`CALLS`, `READS_TABLE`, ...) |

Additional fields: `id`, `source`, `target`, `synthetic` (the evidencing file/line is in a synthetic path or carries the
synthetic marker), `evidence` (source line), `reason` (**mandatory** when confidence is `INFERRED` or `UNRESOLVED`), `attrs`.

## Commit IDs
A *logical repo* is a name in `config/repos.yml` mapped to a folder (`path`). In this PoC all logical repos are folders of
one git repository. Each scanner computes the commit ID of its logical repo as

    git log -1 --format=%H -- <that repo's path>

i.e. the last commit that touched the folder. Because that value only describes the scanned files if they match the commit,
**scanners refuse to run when the logical repo's folder has uncommitted changes**
(`git status --porcelain --untracked-files=normal -- <that repo's path>` non-empty, untracked non-ignored files included;
changes in other folders of the git repository do not matter). Edge `commit_id` and fragment `commit_id` both use this value.
If a logical repo is later pointed at a separate checkout, the same command is run inside it.

## Overlay fragments (`--only`)
`--only <file-with-paths>` restricts which files may *emit* nodes and edges. The scanner still builds the node-id map for the
whole logical repo, so an edge from a changed file to a symbol in an unchanged file is emitted with its real target id. Such a
fragment has `overlay: true` and `overlay_files`; its edge endpoints may be absent from the fragment and are resolved by the
loader against the baseline graph. Edges evidenced in unchanged files are not re-emitted (the baseline has them).

## Confidence semantics
* `CONFIRMED_STATIC` – directly evidenced by a symbol/syntax fact in source (resolved call, table reference in DDL, literal-matched route).
* `INFERRED` – a plausible link that depends on runtime behaviour or a heuristic (e.g. an interface call dispatched to its implementation via DI registration). Never promoted.
* `UNRESOLVED` – the target could not be determined (dynamic SQL, config-built route) or does not exist in the scanned scope ("referenced, not found"). `reason` says which.

## Node kinds
`UI_COMPONENT, UI_SERVICE_METHOD, UI_MODEL, HTTP_REQUEST, API_ENDPOINT, SERVICE_METHOD (business layer), DATA_ACCESS_METHOD, METHOD, INTERFACE_METHOD, SQL_REF, SQL_PROC, SQL_VIEW, SQL_TABLE, SQL_COLUMN (reserved), TEST, UNRESOLVED`.
Node id = `{repo}:{kind-slug}:{qualified-name}`; method names include the parameter-type list, so overloads stay distinct.

## Edge types
| Type | Emitted by | Meaning |
|---|---|---|
| `CALLS` | ts-morph, Roslyn | method -> method (type/symbol resolved) |
| `DISPATCHES_TO` | Roslyn | interface method -> implementing method; always `INFERRED` (runtime DI) |
| `USES_TYPE` | ts-morph | component/service -> model type |
| `MAKES_REQUEST` | ts-morph | UI service method -> `HTTP_REQUEST` node (verb + URL template) |
| `ROUTES_TO` | linker (planned) | `HTTP_REQUEST` -> `API_ENDPOINT` (route match, cross-repo) |
| `CALLS_PROCEDURE` | Roslyn, ScriptDom | C# method -> `SQL_REF`, or SQL proc -> proc |
| `RESOLVES_TO` | linker (planned) | `SQL_REF` -> `SQL_PROC` (cross-repo name match), or UNRESOLVED if not found |
| `READS_TABLE` / `WRITES_TABLE` / `READS_VIEW` | ScriptDom | SQL object -> table/view |
| `EXECUTES_DYNAMIC_SQL` | ScriptDom, Roslyn | -> `UNRESOLVED` node; target cannot be known statically |
| `TESTS` | linker (planned) | `TEST` -> covered node; `attrs.mapping_method` = `naming-convention` or `annotation` |

Edges are stored source -> target meaning "depends on". Impact ("who is affected by a change to X") follows edges in
reverse; root-cause tracing ("what does X depend on") follows them forward.
