#!/usr/bin/env bash
# pb - run penpot-agent from a source checkout. Works from any directory (the project = nearest
# .pbridge/ folder), also through symlinks (project folders can link ./pb here).
#
# Installed copies (`uv tool install ...`) put `pb` on PATH instead; this script is for development.
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")")" && pwd)"

# fast path: the venv created by `uv sync`; otherwise let uv create/sync it
if [ -x "$DIR/.venv/bin/python" ]; then
  exec "$DIR/.venv/bin/python" -m pbridge "$@"
fi
exec uv run --project "$DIR" --quiet python -m pbridge "$@"
