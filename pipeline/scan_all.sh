#!/usr/bin/env bash
# Run the scanner matching each logical repo's kind (config/repos.yml), then validate against the schema.
# Refuses to run on a dirty git working tree (scanners enforce this).
set -euo pipefail
cd "$(dirname "$0")/.."
export DOTNET_CLI_TELEMETRY_OPTOUT=1
# Homebrew installs keep the SDK under libexec; set DOTNET_ROOT yourself if your install differs.
[ -z "${DOTNET_ROOT:-}" ] && [ -d /opt/homebrew/opt/dotnet/libexec ] && export DOTNET_ROOT=/opt/homebrew/opt/dotnet/libexec || true
PY="${PYTHON:-.venv/bin/python}"
OUT="${1:-out/graph}"
dotnet build -v q -nologo scanners/sql-scriptdom >/dev/null
dotnet build -v q -nologo scanners/dotnet-roslyn >/dev/null
files=()
while read -r name kind path; do
  case "$kind" in
    sql)      dotnet scanners/sql-scriptdom/bin/Debug/net10.0/SqlScanner.dll --config config --repo "$name" --out "$OUT/$name.json" ;;
    api)      dotnet scanners/dotnet-roslyn/bin/Debug/net10.0/CsScanner.dll  --config config --repo "$name" --out "$OUT/$name.json" ;;
    frontend) node scanners/ts-morph/scan.mjs --config config --repo "$name" --out "$OUT/$name.json" ;;
    *) echo "unknown kind '$kind' for repo $name" >&2; exit 1 ;;
  esac
  files+=("$OUT/$name.json")
done < <("$PY" tools/list_repos.py)
"$PY" tools/validate_graph.py "${files[@]}"
