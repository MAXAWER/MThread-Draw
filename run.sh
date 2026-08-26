#!/usr/bin/env bash
# One-click launcher for macOS and Linux: builds a virtual environment on first
# run, then starts the AutoDraw desktop app.
#
#     ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

PY=venv/bin/python

if [ ! -x "$PY" ]; then
    echo "Creating a virtual environment in venv/ ..."
    python3 -m venv venv

    echo "Installing AutoDraw and its dependencies. This takes a minute the first time ..."
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install -e ".[gui]"
fi

if ! command -v adb >/dev/null 2>&1 && [ -z "${ADB_PATH:-}" ]; then
    echo "Warning: 'adb' is not on your PATH. Install Android platform-tools, or"
    echo "point ADB_PATH at the binary. https://developer.android.com/tools/releases/platform-tools"
fi

exec "$PY" -m autodraw "$@"
