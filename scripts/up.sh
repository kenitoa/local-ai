#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python was not found. Install Python first." >&2
  exit 1
fi

"$PYTHON_BIN" scripts/preflight.py

if [ ! -f ".runtime.env" ]; then
  echo ".runtime.env was not created by scripts/preflight.py." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .runtime.env
set +a

if [ -z "${COMPOSE_FILES:-}" ]; then
  echo "COMPOSE_FILES was not written to .runtime.env." >&2
  exit 1
fi

IFS=':' read -r -a FILES <<< "$COMPOSE_FILES"
ARGS=()
for file in "${FILES[@]}"; do
  if [ ! -f "$file" ]; then
    echo "Compose file not found: $file" >&2
    exit 1
  fi
  ARGS+=("-f" "$file")
done

UP_ARGS=("up")
if [ "${NO_BUILD:-0}" != "1" ]; then
  UP_ARGS+=("--build")
fi
if [ "${DETACH:-0}" = "1" ]; then
  UP_ARGS+=("--detach")
fi

echo "Selected AI device: ${AI_DEVICE:-unknown}"
echo "Selected LLM backend: ${LLM_BACKEND:-unknown}"
echo "Compose files: $COMPOSE_FILES"
echo "Command: docker compose ${ARGS[*]} ${UP_ARGS[*]}"

docker compose "${ARGS[@]}" "${UP_ARGS[@]}" "$@"
