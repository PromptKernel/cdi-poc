#!/usr/bin/env bash
# Thin wrapper: the single local entry point for a PR run. All options are passed to pipeline/run_pr.py (see its --help).
# Advisory by default: exits 0 in every case unless blocking is explicitly enabled and a deterministic policy hits.
set -uo pipefail
cd "$(dirname "$0")/.."
exec "${PYTHON:-.venv/bin/python}" -m pipeline.run_pr "$@"
