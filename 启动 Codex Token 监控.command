#!/bin/zsh

SCRIPT_DIR="/Users/sean_1/codex/codex-tool"
PYTHON_BIN="/opt/homebrew/bin/python3.13"
WIDGET_SCRIPT="$SCRIPT_DIR/codex_token_widget.py"

cd "$SCRIPT_DIR" || exit 1
exec "$PYTHON_BIN" "$WIDGET_SCRIPT"
