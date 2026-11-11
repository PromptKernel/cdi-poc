# Read-only API and explorer

`cdi serve` runs a small FastAPI service over the baseline graph. The explorer (`frontend/`) can read from it live or from a static snapshot.

```
cdi serve [--config .cdi/config.yml] [--store json|neo4j] [--store-path FILE] [--reports-dir out]
          [--host 127.0.0.1] [--port 8000] [--token-env CDI_API_TOKEN] [--cors-origin ORIGIN ...]
```
OpenAPI document: `GET /openapi.json`; interactive docs: `/docs`.

## Guarantees
* **Read-only.** Every route is `GET` (a test enumerates the routes; POST/PUT/PATCH/DELETE answer 405). The API has no code path that writes a store (a test makes the store's write methods raise).
* **Graph data only through `GraphStore.read()`** (JSON file by default, Neo4j if configured). The JSON store is re-read when the file changes; stores that cannot tell are re-read every 5 s.
  Reports and the latest PR comment/status are read from one folder (`--reports-dir`) by validated names only (`[A-Za-z0-9._-]`, no separators), so no other file can be reached.
* **Localhost by default.** `--host` defaults to `127.0.0.1`. Any other host is **refused unless a token is configured**.
* **Optional bearer token.** If the environment variable named by `--token-env` (default `CDI_API_TOKEN`) is set, every `/api` route except `/api/health` needs
  `Authorization: Bearer <token>` (constant-time comparison; the token is never logged or returned). Without it the API is open, which is only acceptable on localhost.
* **CORS** is off unless `--cors-origin` names the browser origins allowed to call the API (GET and the Authorization header only).
* A missing baseline or one with another schema version answers **503** with the reason ("rebuild the baseline"); it never serves a graph it may misread.

## Endpoints
| Route | Returns |
|---|---|
| `GET /api/health` | `{status, auth_required}` (no graph data, no auth) |
| `GET /api/meta` | data source, store kind, baseline freshness (per-repo commit ids, load time, mode, **schema version**), counts, repos |
| `GET /api/graph` | the whole graph in the explorer's format (`meta`, `nodes`, `edges`) |
| `GET /api/nodes?q=&kind=&repo=&limit=` | node search |
| `GET /api/nodes/{id}` | a node with the edges it depends on and the edges that depend on it |
| `GET /api/trace?id=&direction=forward\|reverse&max_depth=` | maximal dependency paths (forward = dependencies, reverse = consumers); at most 200 paths, `truncated` says if more exist |
| `GET /api/reports`, `GET /api/reports/{name}?format=md\|json` | impact reports found in `--reports-dir` |
| `GET /api/pr` | the latest local PR comment and status files |

## Explorer
* **Runtime configuration.** The page reads `config.json` from its own folder when it loads (`{"apiBaseUrl": "http://127.0.0.1:8000"}`); the URL is not a build-time constant, so a
  deployment edits the file, no rebuild. A missing file or `null` means snapshot mode; an invalid file is shown as an error, never ignored. Only `http(s)` URLs are accepted.
* **Data source indicator** in the header: `data source: live API (<url>)` or `data source: snapshot (data/)`. In live mode the snapshot is never read, and vice versa (the e2e test checks the requests).
* **Analyze** page: where the data comes from, the baseline **schema version**, **load time**, how it was built, and the **commit id of every logical repo**. Facts a snapshot predates
  (for example the schema version in an older export) show "not recorded" rather than a made-up value.
* **Token.** When the API answers 401 the page asks for the token; it is kept in `sessionStorage` (this tab only), sent only to the API, never to snapshot files.
* Static snapshot: `cdi export` writes `out/explorer`; `npm run preview` serves it.

## Running it
```
cdi baseline full                                   # JSON baseline at out/baseline.json
CDI_API_TOKEN=... cdi serve --cors-origin http://127.0.0.1:4173
# frontend: build, then put {"apiBaseUrl": "http://127.0.0.1:8000"} in dist/config.json and serve dist/
```
Tests: `backend/tests/test_api.py` (JSON-store baseline, auth on/off, localhost default, read-only, OpenAPI, CORS), `frontend/src/lib/*.test.ts`, and the Playwright projects
`snapshot`, `live` (real `cdi serve` over `frontend/e2e/fixtures/live/baseline.json`) and `live-auth` (token required).
