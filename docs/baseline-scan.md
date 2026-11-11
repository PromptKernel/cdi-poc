# Baseline scan (milestone 2)

Scanners were run from a clean committed tree (`pipeline/scan_all.sh`), then linked and loaded into Neo4j (`pipeline/link_and_load.sh`).
`commit_id` is `git log -1 --format=%H -- <folder>`. Numbers are for the **synthetic-extended sample**; they say nothing about real code.

| Logical repo | Folder | Scanner | commit_id | Files | Nodes | Edges |
|---|---|---|---|---|---|---|
| web | samples/web | ts-morph | 23f6a2631edd015c6912abd5f59c81c5b7ff6a8d | 25 | 42 | 30 |
| api | samples/api | Roslyn | 23f6a2631edd015c6912abd5f59c81c5b7ff6a8d | 15 | 58 | 40 |
| db | samples/db | ScriptDom | 57e1a2ce0dda204615bcf29589b251e1b202e92d | 13 | 14 | 12 |
| linked | (linker) | linker | SHA-1 over the three commit ids above | - | 1 | 43 |

(web and api share a commit id because one commit touched both folders.)

## Linker result
| Edge type | CONFIRMED_STATIC | INFERRED | UNRESOLVED |
|---|---|---|---|
| ROUTES_TO (HTTP request -> API endpoint) | 9 | 0 | 0 |
| RESOLVES_TO (SQL reference -> definition) | 7 | 0 | 1 (`dbo.spArchiveEmployee`: referenced, not found) |
| TESTS (test -> covered node) | 4 (annotation) | 22 (naming/file convention) | 0 |

Scanner-level UNRESOLVED edges (not linkable): 2 web requests (config-built route, whole-URL-is-a-parameter), 3 C# dynamic/inline SQL, 1 SQL dynamic SQL.

## Checks
* All outputs pass `schema/graph.schema.json` (0 schema errors, 0 dangling endpoints, 0 duplicate node ids).
* Neo4j holds 115 nodes and 125 relationships (= 42 + 58 + 14 + 1 nodes, 30 + 40 + 12 + 43 edges); none skipped.
* `tools/compare_expected.py`: 82 of 82 hand-written expected edges found (recall 100% **on this synthetic sample**), 0 guard violations, 0 test-annotation mismatches.
* `pytest tests`: 80 passed (includes 5 Neo4j integration tests, run against the local container).
