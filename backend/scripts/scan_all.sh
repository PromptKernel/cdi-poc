#!/usr/bin/env bash
# Run the scanner plugin selected for each logical repo in .cdi/config.yml, then validate against the schema.
# Run from the TARGET repository's root. Scanners refuse to run when a logical repo's folder is dirty. Options: --config PATH, --out DIR.
set -euo pipefail
export DOTNET_CLI_TELEMETRY_OPTOUT=1
[ -z "${DOTNET_ROOT:-}" ] && [ -d /opt/homebrew/opt/dotnet/libexec ] && export DOTNET_ROOT=/opt/homebrew/opt/dotnet/libexec || true
exec "${PYTHON:-python}" -m cdi.pipeline.scan_all "$@"
