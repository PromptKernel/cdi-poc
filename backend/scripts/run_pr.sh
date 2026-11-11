#!/usr/bin/env bash
# Thin wrapper: the single local entry point for a PR run. All options are passed to cdi.pipeline.run_pr (see its --help).
# Advisory by default: exits 0 in every case unless blocking is explicitly enabled and a deterministic policy hits.
set -uo pipefail
exec "${PYTHON:-python}" -m cdi.pipeline.run_pr "$@"
