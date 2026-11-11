#!/usr/bin/env bash
# Link the scanner fragments (out/graph/*.json) and load everything into Neo4j (`graph` section of .cdi/config.yml).
# Run from the target repository's root. Needs: scan_all.sh already run; NEO4J_PASSWORD exported for the Neo4j load.
set -euo pipefail
PY="${PYTHON:-python}"
"$PY" -m cdi.linker.link --graph out/graph
"$PY" -m cdi.validate out/graph/*.json
if [ -n "${NEO4J_PASSWORD:-}" ]; then
  "$PY" -m cdi.graph.load_neo4j --graph out/graph --reset
else
  echo "NEO4J_PASSWORD not set: skipping the Neo4j load" >&2
fi
