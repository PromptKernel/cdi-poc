# Baseline scan (milestone 1)

Scanners were run from a clean committed tree (`pipeline/scan_all.sh`). `commit_id` is `git log -1 --format=%H -- <folder>`.
Numbers are for the **synthetic-extended sample**; they say nothing about real code.

| Logical repo | Folder | Scanner | commit_id | Files | Nodes | Edges |
|---|---|---|---|---|---|---|
| web | samples/web | ts-morph | 5c78d13af68224acb6b472d8612823bc11f55835 | 25 | 38 | 29 |
| api | samples/api | Roslyn | 043cacfbccf97294540e2c800e1e5856015d923a | 14 | 48 | 32 |
| db | samples/db | ScriptDom | 57e1a2ce0dda204615bcf29589b251e1b202e92d | 13 | 14 | 12 |

All three outputs pass `schema/graph.schema.json` (0 schema errors, 0 dangling endpoints, 0 duplicate node ids).
A run with an uncommitted file in the tree exits with code 2 and a refusal message.
