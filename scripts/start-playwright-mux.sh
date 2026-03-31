#!/usr/bin/env bash
# Launcher for playwright-mux-parallel that resolves the Chrome profile path
# at runtime using $HOME (or $CHROME_AUTOMATION_PROFILE if set).
# Used by .claude/mcp.json so the path is never hardcoded for a specific user.
#
# The multiplexer only supports a single --init-script argument (last one wins).
# Both PostHog scripts are concatenated into a single temp file so the bundle
# (which defines window.posthog) is guaranteed to run before the init code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROFILE_DIR="${CHROME_AUTOMATION_PROFILE:-$HOME/.config/chrome-automation}"

# Read POSTHOG_DISTINCT_ID from .env so browser sessions use the same identity
# as server-side pipeline events — enabling PostHog to link session replays to
# scout_complete / pipeline_complete events.
PH_DISTINCT_ID=""
PH_USER_NAME=""
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  PH_DISTINCT_ID=$(grep -E "^POSTHOG_DISTINCT_ID=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '[:space:]' || true)
  PH_USER_NAME=$(grep -E "^POSTHOG_USER_NAME=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '[:space:]' || true)
fi

# Download PostHog's lazy-recorder (rrweb) so it's available immediately when
# startSessionRecording() is called. Without this, PostHog fetches it from CDN
# on every page navigation (~350ms), creating a gap where clicks aren't recorded.
RECORDER_SCRIPT="/tmp/posthog-lazy-recorder.js"
PH_VERSION=$(grep -oP 'us="[^"]*"' "$SCRIPT_DIR/posthog-bundle.js" | head -1 | grep -oP '"[^"]*"' | tr -d '"')
if [ -n "$PH_VERSION" ]; then
  # Re-download only if bundle is newer than cached recorder (version change)
  if [ ! -f "$RECORDER_SCRIPT" ] || [ "$SCRIPT_DIR/posthog-bundle.js" -nt "$RECORDER_SCRIPT" ]; then
    curl -sSfL "https://us-assets.i.posthog.com/static/lazy-recorder.js?v=${PH_VERSION}" \
      -o "$RECORDER_SCRIPT" 2>/dev/null || {
      echo "[WARN] Failed to download lazy-recorder.js, falling back to CDN lazy-load" >&2
      RECORDER_SCRIPT=""
    }
  fi
else
  echo "[WARN] Could not extract PostHog version from bundle" >&2
  RECORDER_SCRIPT=""
fi

# Concatenate bundle + recorder + config + init into a single file.
COMBINED_SCRIPT="/tmp/posthog-mux-combined.js"
{
  cat "$SCRIPT_DIR/posthog-bundle.js"
  echo ";"
  # Prebundle lazy-recorder so __PosthogExtensions__.initSessionRecording is
  # defined before posthog.init() runs — rrweb starts on the fast path with
  # zero delay, capturing clicks from the very first moment on every page.
  if [ -n "$RECORDER_SCRIPT" ] && [ -f "$RECORDER_SCRIPT" ]; then
    cat "$RECORDER_SCRIPT"
    echo ";"
  fi
  # Inject distinct ID as a global so posthog-init.js uses the same identity
  # as server-side pipeline events (enables linking session replays to events).
  echo "window.__PH_DISTINCT_ID = '${PH_DISTINCT_ID}';"
  echo "window.__PH_USER_NAME = '${PH_USER_NAME}';"
  cat "$SCRIPT_DIR/posthog-init.js"
} > "$COMBINED_SCRIPT"

exec node "$PROJECT_ROOT/playwright-mcp/packages/playwright-mcp-multiplexer/dist/cli.js" \
  --browser=chrome \
  --headed \
  "--user-data-dir=$PROFILE_DIR" \
  "--init-script=$COMBINED_SCRIPT" \
  --bypass-csp \
  "$@"
