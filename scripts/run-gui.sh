#!/usr/bin/env bash
# doc-translator - one-click GUI launcher (macOS/Linux).
#
# First run:
#   - installs uv (into ~/.local/bin) if missing
#   - runs `uv sync`
#   - downloads babeldoc layout models on first translation (needs network)
#
# Defaults:
#   Port 7860, bound to 0.0.0.0 so the machine acts as a LAN server.
#   Other hosts can reach the UI at http://<this-host-ip>:7860 .
#
# Override via env vars before running:
#   DT_PORT=18080 ./run-gui.sh
#   DT_AUTH=/path/to/auth.txt ./run-gui.sh   # file with `user:password` lines
set -e

cd "$(dirname "$0")/.."

DT_PORT="${DT_PORT:-7860}"

if ! command -v uv >/dev/null 2>&1; then
    echo "[1/3] Installing uv ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "[2/3] Syncing dependencies ..."
uv sync

echo "[3/3] Launching GUI on http://0.0.0.0:${DT_PORT} ..."
if [ -n "${DT_AUTH:-}" ]; then
    exec uv run translator --gui --server-port "${DT_PORT}" --auth-file "${DT_AUTH}"
else
    exec uv run translator --gui --server-port "${DT_PORT}"
fi
