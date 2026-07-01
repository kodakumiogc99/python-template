#!/usr/bin/env bash
# run.sh — Linux/macOS launcher for create_project.py
#
# Does NOT require Python to be pre-installed.
# Installs uv (a Rust binary) if missing, then uses uv to run the script.
# uv will download Python automatically if needed.
#
# Usage (no chmod needed — call via bash directly):
#   bash run.sh                              # interactive
#   bash run.sh my-tool                      # pre-fill name
#   bash run.sh my-api --type api --yes      # non-interactive
#   bash run.sh --help
#
# Optional: make it directly executable (only needed once, or via git)
#   chmod +x run.sh && ./run.sh
#   git add --chmod=+x run.sh  # persist executable bit in git for all cloners

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Install uv if missing ─────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "uv not found. Installing..."

    if command -v curl &>/dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget &>/dev/null; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "ERROR: Neither curl nor wget found."
        echo "  Install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi

    # Refresh PATH in this session
    for extra in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -d "$extra" ] && [[ ":$PATH:" != *":$extra:"* ]]; then
            export PATH="$extra:$PATH"
        fi
    done

    if ! command -v uv &>/dev/null; then
        echo "ERROR: uv installed but not found in PATH."
        echo "  Please restart your terminal and run this script again."
        exit 1
    fi

    echo "uv installed successfully."
    echo ""
fi

# ── Run the script via uv ─────────────────────────────────────
# uv will download Python automatically if not present (guided by PEP 723 header)
exec uv run "$SCRIPT_DIR/create_project.py" "$@"
