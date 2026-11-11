#!/usr/bin/env bash
# Recreate the six LOCAL demo branches (pr-a-sp-body ... pr-f-route) from a clean main, and optionally generate the impact reports.
#   scripts/make_demo_branches.sh                   create/re-point the branches only
#   scripts/make_demo_branches.sh --reports neo4j   also write out/report-<branch>.md/.json using the baseline stored in Neo4j
#   scripts/make_demo_branches.sh --reports files   same, using the baseline files in out/graph (run `python -m cdi.pipeline.baseline full --no-neo4j` first)
# The branches are never pushed. Each holds ONE commit off main (defined in .cdi/scenarios.yml). Existing branches with these names are re-pointed
# (git worktree add -B), so run this again after main moves to avoid the "PR branch is based on an older target" warning.
# Worktrees are created at named paths under out/work and removed with `git worktree remove` on exactly those paths.
set -euo pipefail
PY="${PYTHON:-python}"   # run from the target repository root
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || { echo "run this from the main branch" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "main has uncommitted changes; commit or stash them first" >&2; exit 1; }

"$PY" -m cdi.eval.scenarios
if [ "${1:-}" = "--reports" ]; then
  mode="${2:-neo4j}"
  [ "$mode" = "neo4j" ] && [ -z "${NEO4J_PASSWORD:-}" ] && { echo "set NEO4J_PASSWORD (and load the baseline: python -m cdi.pipeline.baseline full)" >&2; exit 1; }
  for b in $("$PY" -c "from cdi.eval import scenarios; print(' '.join(scenarios.load_scenarios()))"); do
    "$PY" -m cdi.impact.cli --target main --pr "$b" --name "$b" --baseline "$mode"
  done
fi
