#!/usr/bin/env bash
# Conduit launcher — used by install.sh and the .desktop file

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/venv/bin/python3"

exec "$PYTHON" "$SCRIPT_DIR/desktop.py" "$@"
