#!/usr/bin/env bash
# Run the scanner matching each logical repo's kind (config/repos.yml), then validate against the schema.
# Run from the TARGET repository's root (the directory that holds config/ and the repos). Scanners refuse to run when a logical repo's folder is dirty.
set -euo pipefail
BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
# Homebrew installs keep the SDK under libexec; set DOTNET_ROOT yourself if your install differs.
[ -z "${DOTNET_ROOT:-}" ] && [ -d /opt/homebrew/opt/dotnet/libexec ] && export DOTNET_ROOT=/opt/homebrew/opt/dotnet/libexec || true
PY="${PYTHON:-python}"
OUT="${1:-out/graph}"
dotnet build -v q -nologo "$BACKEND/scanners/sql-scriptdom" >/dev/null
dotnet build -v q -nologo "$BACKEND/scanners/dotnet-roslyn" >/dev/null
files=()
while read -r name kind path; do
  case "$kind" in
    sql)      dotnet "$BACKEND/scanners/sql-scriptdom/bin/Debug/net10.0/SqlScanner.dll" --config config --repo "$name" --out "$OUT/$name.json" ;;
    api)      dotnet "$BACKEND/scanners/dotnet-roslyn/bin/Debug/net10.0/CsScanner.dll"  --config config --repo "$name" --out "$OUT/$name.json" ;;
    frontend) node "$BACKEND/scanners/ts-morph/scan.mjs" --config config --repo "$name" --out "$OUT/$name.json" ;;
    *) echo "unknown kind '$kind' for repo $name" >&2; exit 1 ;;
  esac
  files+=("$OUT/$name.json")
done < <("$PY" -m cdi.list_repos)
"$PY" -m cdi.validate "${files[@]}"
