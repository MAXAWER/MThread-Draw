#!/usr/bin/env bash
# One-click launcher for macOS and Linux: builds a virtual environment on first
# run, then starts the MThreadDraw desktop app.
#
#     ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

PY=venv/bin/python

if [ ! -x "$PY" ]; then
    echo "Creating a virtual environment in venv/ ..."
    python3 -m venv venv

    echo "Installing MThreadDraw and its dependencies. This takes a minute the first time ..."
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install -e ".[gui]"
fi

# adb, if this machine has none of its own. Downloaded once, from Google.
if ! command -v adb >/dev/null 2>&1 && [ -z "${ADB_PATH:-}" ] && [ ! -x platform-tools/adb ]; then
    echo "Fetching adb ..."
    "$PY" tools/fetch_platform_tools.py
fi

exec "$PY" -m mthread_draw "$@"
