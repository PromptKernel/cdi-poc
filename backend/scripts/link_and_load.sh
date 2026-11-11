#!/usr/bin/env bash
# Link the scanner fragments (out/graph/*.json) and publish the graph to the baseline store (`graph.store` in .cdi/config.yml: json by default, neo4j optional).
# Run from the target repository's root, after scan_all.sh. For Neo4j, export the variable named by graph.neo4j.password_env (default NEO4J_PASSWORD).
set -euo pipefail
PY="${PYTHON:-python}"
"$PY" -m cdi.linker.link --graph out/graph
"$PY" -m cdi.validate out/graph/*.json
"$PY" -m cdi.store.publish --graph out/graph "$@"
