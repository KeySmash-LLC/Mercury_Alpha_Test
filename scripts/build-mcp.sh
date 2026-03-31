#!/usr/bin/env bash
# build-mcp.sh — Build the Playwright MCP multiplexer from the local fork.
#
# Run once after cloning, or after pulling submodule updates.
# After building, the multiplexer is available via .claude/mcp.json automatically.
#
# Usage:
#   ./scripts/build-mcp.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PW_MCP="$REPO_ROOT/playwright-mcp"
PW_FORK="$PW_MCP/playwright"
MUX="$PW_MCP/packages/playwright-mcp-multiplexer"

# ── Ensure submodules are initialized ───────────────────────────────────────

if [ ! -f "$MUX/package.json" ]; then
  echo "Initializing submodules..."
  (cd "$REPO_ROOT" && git submodule update --init --recursive)
fi

# ── Install dependencies ───────────────────────────────────────────────────

echo "Installing dependencies..."
(cd "$PW_MCP" && npm install 2>&1 | tail -3)

# ── Build playwright fork ──────────────────────────────────────────────────

if [ ! -f "$PW_FORK/packages/playwright/lib/mcp/program.js" ]; then
  echo "Building playwright fork (first time, may take a minute)..."
  (cd "$PW_MCP/packages/playwright-mcp" && npm run build 2>&1 | tail -3)
fi

# ── Build multiplexer ──────────────────────────────────────────────────────

echo "Building multiplexer..."
(cd "$MUX" && npx tsc 2>&1)

echo ""
echo "Build complete. The multiplexer is configured in .claude/mcp.json."
echo "Claude agents will use it automatically."
