#!/usr/bin/env bash
# Link the scanner fragments (out/graph/*.json) and load everything into Neo4j (config/graph.yml).
# Needs: pipeline/scan_all.sh already run; NEO4J_PASSWORD exported; `docker compose -f graph/docker-compose.yml up -d` running.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
"$PY" -m linker.link --config config --graph out/graph
"$PY" tools/validate_graph.py out/graph/web.json out/graph/api.json out/graph/db.json out/graph/linked.json
if [ -n "${NEO4J_PASSWORD:-}" ]; then
  "$PY" -m graph.load_neo4j --config config --graph out/graph --reset
else
  echo "NEO4J_PASSWORD not set: skipping the Neo4j load" >&2
fi
