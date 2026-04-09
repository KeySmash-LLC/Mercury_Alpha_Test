#!/usr/bin/env bash
# setup.sh — One-shot bootstrap for the Mercury Alpha Test pipeline.
#
# Usage:
#   git clone <repo-url> && cd Mercury_Alpha_Test && ./setup.sh
#
# Idempotent — safe to re-run. Skips steps that are already done.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ── Helpers ────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
step() { echo -e "\n${BOLD}[$1/$TOTAL_STEPS] $2${NC}"; }

need_cmd() {
  if command -v "$1" &>/dev/null; then
    return 1  # already installed
  fi
  return 0
}

TOTAL_STEPS=8

# ── Step 1: System dependencies ───────────────────────────────────────────

step 1 "Checking system dependencies"

NEED_APT=false
APT_PACKAGES=()

# Chrome
if need_cmd google-chrome-stable; then
  echo ""
  echo "  Chrome is not installed. Installing requires adding the Google apt repo."
  read -rp "  Install google-chrome-stable? [Y/n] " ans
  if [[ "${ans:-Y}" =~ ^[Yy]$ ]]; then
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add - 2>/dev/null
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
    NEED_APT=true
    APT_PACKAGES+=(google-chrome-stable)
  else
    warn "Skipping Chrome — browser agents won't work without it"
  fi
else
  ok "Chrome: $(google-chrome-stable --version 2>/dev/null | head -1)"
fi

# Xvfb
if ! [ -f /usr/bin/Xvfb ]; then
  APT_PACKAGES+=(xvfb)
  NEED_APT=true
else
  ok "Xvfb: installed"
fi

# Node.js
if need_cmd node; then
  echo ""
  echo "  Node.js is not installed. The multiplexer requires Node 18+."
  read -rp "  Install Node.js 22.x via nodesource? [Y/n] " ans
  if [[ "${ans:-Y}" =~ ^[Yy]$ ]]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - 2>/dev/null
    APT_PACKAGES+=(nodejs)
    NEED_APT=true
  else
    fail "Skipping Node.js — multiplexer build will fail"
  fi
else
  ok "Node.js: $(node --version)"
fi

# Python 3
if need_cmd python3; then
  APT_PACKAGES+=(python3 python3-pip python3-venv)
  NEED_APT=true
else
  ok "Python: $(python3 --version)"
fi

# Install everything that needs apt in one pass
if $NEED_APT; then
  echo ""
  echo "  Installing system packages: ${APT_PACKAGES[*]}"
  sudo apt-get update -qq
  sudo apt-get install -y "${APT_PACKAGES[@]}"
  ok "System packages installed"
fi

# tectonic (standalone binary, not in apt)
if need_cmd tectonic; then
  echo ""
  echo "  Installing tectonic (LaTeX compiler)..."
  mkdir -p ~/.local/bin
  TECTONIC_URL=$(curl -s https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest \
    | grep -o '"browser_download_url": "[^"]*x86_64-unknown-linux-musl[^"]*"' \
    | grep -o 'https://[^"]*')
  curl -fsSL "$TECTONIC_URL" | tar xz -C ~/.local/bin
  export PATH="$HOME/.local/bin:$PATH"
  # Ensure it's on PATH permanently
  if ! grep -q 'local/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  fi
  ok "tectonic: $(tectonic --version)"
else
  ok "tectonic: $(tectonic --version 2>/dev/null | head -1)"
fi

# WSL display check
if grep -qi microsoft /proc/version 2>/dev/null; then
  if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    warn "WSL2 detected but no DISPLAY set — browser windows may not appear"
    warn "Check that WSLg is working, or set DISPLAY manually"
  else
    ok "Display: DISPLAY=${DISPLAY:-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"
  fi
fi

# ── Step 2: Git submodules + Playwright MCP build ─────────────────────────

step 2 "Building Playwright MCP multiplexer"

if [ -f "$REPO_ROOT/playwright-mcp/packages/playwright-mcp-multiplexer/dist/cli.js" ]; then
  ok "Multiplexer already built"
else
  if [ ! -d "$REPO_ROOT/playwright-mcp" ]; then
    warn "playwright-mcp/ directory not found"
    echo "  The Playwright MCP fork needs to be set up as a git submodule."
    echo "  If you have the submodule URL, run:"
    echo "    git submodule add <url> playwright-mcp"
    echo "    git submodule update --init --recursive"
    echo "    ./scripts/build-mcp.sh"
    warn "Skipping multiplexer build — add the submodule and re-run setup.sh"
  else
    echo "  Running scripts/build-mcp.sh..."
    bash "$REPO_ROOT/scripts/build-mcp.sh"
    ok "Multiplexer built"
  fi
fi

# ── Step 3: Python virtual environment + deps ─────────────────────────────

step 3 "Setting up Python environment"

if [ ! -d "$REPO_ROOT/.venv" ]; then
  echo "  Creating virtual environment..."
  python3 -m venv "$REPO_ROOT/.venv"
  ok "Virtual environment created at .venv/"
else
  ok "Virtual environment exists"
fi

source "$REPO_ROOT/.venv/bin/activate"

# Install deps (pip is fast enough for 3 packages)
echo "  Installing Python packages..."
pip install -q pyyaml requests posthog 2>&1 | tail -1
ok "Python packages installed"

# ── Step 4: Environment file ──────────────────────────────────────────────

step 4 "Setting up .env"

ENV_FILE="$REPO_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
  ok ".env already exists"
else
  echo "  Creating .env file..."

  # Prompt for PostHog key (the only required one)
  echo ""
  read -rp "  PostHog API key (required for analytics, or press Enter to skip): " ph_key
  read -rp "  Your display name for analytics (optional): " ph_name

  PH_DISTINCT_ID=$(python3 -c "import uuid; print(uuid.uuid4())")

  cat > "$ENV_FILE" <<EOF
# Pipeline analytics
POSTHOG_API_KEY=${ph_key}
POSTHOG_USER_NAME=${ph_name}
POSTHOG_DISTINCT_ID=${PH_DISTINCT_ID}

# Optional model API keys
# DEEP_SEEK_API_KEY=
# GOOGLE_API_KEY=

# Set to false to disable telemetry
# ANONYMIZED_TELEMETRY=false
EOF

  ok ".env created (analytics ID: $PH_DISTINCT_ID)"
fi

# ── Step 5: SQLite database ───────────────────────────────────────────────

step 5 "Initializing database"

mkdir -p "$REPO_ROOT/data/jobs" "$REPO_ROOT/data/contracts"

if [ -f "$REPO_ROOT/data/explorer.db" ]; then
  ok "Database already exists"
else
  echo "  Creating explorer.db from schema..."
  python3 "$REPO_ROOT/scripts/import_to_db.py"
  ok "Database initialized"
fi

# ── Step 6: Claude Code configuration ─────────────────────────────────────

step 6 "Configuring Claude Code"

# .claude directory
mkdir -p "$REPO_ROOT/.claude/agents" "$REPO_ROOT/.claude/hooks"

# MCP config — use the launcher script so paths resolve at runtime
MCP_FILE="$REPO_ROOT/.mcp.json"
if [ -f "$MCP_FILE" ]; then
  ok ".mcp.json already exists"
else
  cat > "$MCP_FILE" <<MCPEOF
{
  "mcpServers": {
    "playwright-mux-parallel": {
      "command": "bash",
      "args": [
        "$REPO_ROOT/scripts/start-playwright-mux.sh",
        "--max-instances=10"
      ]
    },
    "explorer-db": {
      "command": "uvx",
      "args": [
        "mcp-server-sqlite",
        "--db-path",
        "$REPO_ROOT/data/explorer.db"
      ]
    }
  }
}
MCPEOF
  ok ".mcp.json created"
fi

# Credentials template
if [ ! -f "$REPO_ROOT/knowledge/credentials.yaml" ]; then
  cp "$REPO_ROOT/knowledge/credentials.yaml.example" "$REPO_ROOT/knowledge/credentials.yaml"
  ok "knowledge/credentials.yaml created from template — fill in your ATS passwords"
else
  ok "knowledge/credentials.yaml exists"
fi

# Setup directory for resume drop
mkdir -p "$REPO_ROOT/setup"

# ── Step 7: .gitignore ────────────────────────────────────────────────────

step 7 "Checking .gitignore"

GITIGNORE="$REPO_ROOT/.gitignore"
if [ ! -f "$GITIGNORE" ]; then
  cat > "$GITIGNORE" <<'EOF'
# Secrets
.env
knowledge/credentials.yaml

# Python
.venv/
__pycache__/
*.pyc

# Data (user-specific)
data/explorer.db
data/jobs/
data/contracts/

# Build artifacts
playwright-mcp/

# Logs
logs/

# Chrome profile
.config/chrome-automation/
EOF
  ok ".gitignore created"
else
  ok ".gitignore already exists"
fi

# ── Step 8: Chrome profile setup ──────────────────────────────────────────

step 8 "Chrome profile for job site authentication"

PROFILE_DIR="${CHROME_AUTOMATION_PROFILE:-$HOME/.config/chrome-automation}"

if [ -d "$PROFILE_DIR/Default" ]; then
  ok "Chrome profile already exists at $PROFILE_DIR"
  echo ""
  read -rp "  Re-authenticate (log into job sites again)? [y/N] " ans
  if [[ "${ans:-N}" =~ ^[Yy]$ ]]; then
    bash "$REPO_ROOT/scripts/setup-chrome-profile.sh"
  fi
else
  echo ""
  echo "  Chrome will open with tabs for LinkedIn, Indeed, and Upwork."
  echo "  Log into each site, then close Chrome to save the profile."
  echo ""
  read -rp "  Ready to open Chrome? [Y/n] " ans
  if [[ "${ans:-Y}" =~ ^[Yy]$ ]]; then
    bash "$REPO_ROOT/scripts/setup-chrome-profile.sh"
    if [ -d "$PROFILE_DIR/Default" ]; then
      ok "Chrome profile saved"
    else
      warn "Chrome profile not found — you may need to run this step again"
    fi
  else
    warn "Skipped — run ./scripts/setup-chrome-profile.sh later"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Setup complete!${NC}"
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo ""

# Run verification checks
ISSUES=0

echo -e "${BOLD}Verification:${NC}"

if command -v tectonic &>/dev/null; then ok "tectonic"; else fail "tectonic not found"; ((ISSUES++)) || true; fi
if command -v google-chrome-stable &>/dev/null; then ok "Chrome"; else fail "Chrome not found"; ((ISSUES++)) || true; fi
if [ -f /usr/bin/Xvfb ]; then ok "Xvfb"; else fail "Xvfb not found"; ((ISSUES++)) || true; fi
if command -v node &>/dev/null; then ok "Node.js"; else fail "Node.js not found"; ((ISSUES++)) || true; fi
if [ -f "$REPO_ROOT/data/explorer.db" ]; then ok "Database"; else fail "Database not initialized"; ((ISSUES++)) || true; fi
if [ -f "$REPO_ROOT/.mcp.json" ]; then ok ".mcp.json"; else fail ".mcp.json missing"; ((ISSUES++)) || true; fi
if [ -f "$REPO_ROOT/.env" ]; then ok ".env"; else fail ".env missing"; ((ISSUES++)) || true; fi
if [ -d "$PROFILE_DIR/Default" ]; then ok "Chrome profile"; else warn "Chrome profile — run setup-chrome-profile.sh"; fi

MUX_CLI="$REPO_ROOT/playwright-mcp/packages/playwright-mcp-multiplexer/dist/cli.js"
if [ -f "$MUX_CLI" ]; then ok "Playwright multiplexer"; else warn "Multiplexer not built — add submodule and run scripts/build-mcp.sh"; fi

echo ""
if [ $ISSUES -eq 0 ]; then
  echo -e "${GREEN}All checks passed.${NC}"
else
  echo -e "${YELLOW}$ISSUES issue(s) found — see above.${NC}"
fi

echo ""
echo -e "${BOLD}Next steps:${NC}"
echo "  1. Drop your resume (PDF/TXT/MD) into setup/"
echo "  2. Start Claude Code:  claude"
echo '  3. Ask: "Set up the pipeline with my resume. I'\''m in <City, State>. <Work auth>."'
echo "  4. Fill in knowledge/credentials.yaml with your ATS passwords"
echo "  5. Start hunting:  python scripts/pipeline 10"
echo ""
