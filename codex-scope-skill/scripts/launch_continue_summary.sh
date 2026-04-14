#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="$SCRIPT_DIR/codex_continue_summary.py"

find_python() {
  local candidate=""

  if [[ -n "${CODEX_SCOPE_PYTHON:-}" && -x "${CODEX_SCOPE_PYTHON}" ]]; then
    printf '%s\n' "${CODEX_SCOPE_PYTHON}"
    return 0
  fi

  for candidate in \
    "$SCRIPT_DIR/../../.venv/bin/python" \
    "$SCRIPT_DIR/../.venv/bin/python" \
    "/opt/homebrew/bin/python3.13" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3.13" \
    "/usr/local/bin/python3" \
    "$HOME/.pyenv/shims/python3" \
    "$HOME/.pyenv/shims/python"
  do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  if command -v python3 >/dev/null 2>&1; then
    candidate="$(command -v python3)"
    if [[ "$candidate" != "/usr/bin/python3" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "$(command -v python)"
    return 0
  fi

  return 1
}

PYTHON_BIN="$(find_python || true)"

if [[ -z "$PYTHON_BIN" ]]; then
  cat >&2 <<'EOF'
Could not find a usable Python runtime for Codex Scope.

Recommended fixes:
1. Install Python 3.11+ with Tk support.
2. Or create a local virtualenv at .venv.
3. Or set CODEX_SCOPE_PYTHON to your preferred interpreter path.

Examples:
  export CODEX_SCOPE_PYTHON=/opt/homebrew/bin/python3.13
  bash scripts/launch_continue_summary.sh
EOF
  exit 1
fi

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" "$TARGET_SCRIPT" "$@"
