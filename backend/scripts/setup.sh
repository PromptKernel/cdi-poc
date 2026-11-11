#!/usr/bin/env bash
# One-time setup from the repository root (also what `make setup` runs):
#   1. a Python virtual environment (default .venv; override with VENV=...)
#   2. the backend: pinned requirements, then `pip install -e backend` (gives the `cdi` command)
#   3. the .NET scanners (Roslyn, ScriptDom) built once
#   4. `npm ci` for the TypeScript scanner and for the frontend
# Needs: python3 >= 3.10, git, the .NET 10 SDK, Node >= 22.12 with npm. Re-running is safe (idempotent).
set -euo pipefail
cd "$(dirname "$0")/../.."
VENV="${VENV:-.venv}"
PYTHON="${PYTHON:-python3}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "setup: '$1' not found. $2" >&2; exit 1; }; }
need "$PYTHON" "Install Python 3.10 or newer."
need git "Install git."
need dotnet "Install the .NET 10 SDK (https://dotnet.microsoft.com/download)."
need node "Install Node 22.12 or newer."
need npm "Install npm (it ships with Node)."

"$PYTHON" - <<'PY' || { echo "setup: Python 3.10 or newer is required" >&2; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY
dotnet --list-sdks | grep -q '^10\.' || { echo "setup: the .NET 10 SDK is required (found: $(dotnet --version))" >&2; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a>22||(a===22&&b>=12)) ? 0 : 1)' \
  || { echo "setup: Node 22.12 or newer is required (found $(node --version))" >&2; exit 1; }

echo "==> Python environment ($VENV)"
[ -x "$VENV/bin/python" ] || "$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r backend/requirements.txt
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -e backend

echo "==> .NET scanners"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
dotnet build -nologo -v q backend/scanners/sql-scriptdom
dotnet build -nologo -v q backend/scanners/dotnet-roslyn

echo "==> npm ci (TypeScript scanner, frontend)"
(cd backend/scanners/ts-morph && npm ci --no-audit --no-fund)
(cd frontend && npm ci --no-audit --no-fund)

echo "==> done. Next: make test | make audit | make smoke   (see README)"
"$VENV/bin/cdi" --help >/dev/null && echo "cdi is installed: $VENV/bin/cdi"
