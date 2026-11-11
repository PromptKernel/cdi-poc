// The smoke test runs against a committed, generic explorer dataset (e2e/fixtures/explorer: graph.json, reports, PR files) served by the
// preview middleware through EXPLORER_DATA_DIR (see playwright.config.ts). No Python, Neo4j or target repository is needed.
// The same UI against real pipeline output is exercised by the end-to-end smoke script (a later phase).
export default async function setup() {}
