# Environment Setup

System and infrastructure setup: dependencies, Chrome profile, database, and MCP configuration.

---

## Automated Setup (Recommended)

The setup script handles everything — system dependencies, Playwright build, Python environment, database initialization, configuration files, and Chrome profile authentication:

```bash
git clone --recursive <repo-url>
cd Mercury_Alpha_Test
./setup.sh
```

The script is idempotent — safe to re-run if something fails partway through. It prompts before installing anything that requires `sudo` and skips steps that are already complete.

After setup finishes, continue with:
1. Drop your resume into `setup/` and run the Setup Agent (see [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md))
2. Fill in `knowledge/credentials.yaml` with your ATS login passwords
3. Start the pipeline: `python scripts/pipeline 10`

The rest of this document covers **manual setup and troubleshooting** — you only need it if the setup script fails or you want to understand what each step does.

---

## Prerequisites

Install these before anything else (or let `setup.sh` handle them).

On a fresh Linux install:
```bash
sudo apt update && sudo apt upgrade -y
```

### Claude Code

This project is orchestrated by Claude Code. Install it first:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Requires an [Anthropic API key](https://console.anthropic.com/). On first run, `claude` will prompt you to authenticate.

### System packages

These are installed automatically by `setup.sh`. For manual installation:

```bash
# Chrome (for browser automation)
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update && sudo apt-get install -y google-chrome-stable

# Xvfb (required by the multiplexer for headless probe instances — even in --headed mode)
sudo apt-get install -y xvfb

# Node.js 18+ (for the multiplexer build and runtime)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

# Python 3 + pip (for pipeline scripts and SQLite MCP server)
sudo apt-get install -y python3 python3-pip python3-venv

# tectonic (LaTeX compiler for resume/cover letter PDFs)
mkdir -p ~/.local/bin
curl -fsSL $(curl -s https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest \
  | grep -o '"browser_download_url": "[^"]*x86_64-unknown-linux-musl[^"]*"' \
  | grep -o 'https://[^"]*') \
  | tar xz -C ~/.local/bin
# Ensure ~/.local/bin is on your PATH (add to ~/.bashrc if needed):
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && export PATH="$HOME/.local/bin:$PATH"
```

### WSL display (WSL2 only)

Browser windows open on your Windows desktop. Verify these are set:

```bash
echo $DISPLAY          # should be :0 or similar
echo $WAYLAND_DISPLAY  # should be wayland-0 or similar
```

If blank, your WSL2 distro may need a display server configured (e.g. WSLg, VcXsrv, or X410).

### Verify Xvfb path explicitly

`which Xvfb` can return nothing even when it's installed. Confirm directly:

```bash
/usr/bin/Xvfb -help 2>&1 | head -1
# Expected: "use: X [:<display>] [option]"
```

The node process finds it at `/usr/bin/Xvfb` regardless of your shell PATH.

---

## Manual Setup Steps

These steps are what `setup.sh` automates. Use them for troubleshooting or if you prefer manual control.

### Step 1 — Clone and initialize submodules

```bash
git clone <repo-url> Mercury_Alpha_Test
cd Mercury_Alpha_Test
git submodule update --init --recursive
```

### Step 2 — Build the Playwright MCP Multiplexer

```bash
./scripts/build-mcp.sh
```

This initializes submodules, installs npm dependencies, builds the Playwright fork, and compiles the multiplexer TypeScript. Re-run after pulling submodule updates.

Verify the build output exists:

```bash
ls playwright-mcp/packages/playwright-mcp-multiplexer/dist/cli.js
```

### Step 3 — Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyyaml requests posthog
```

### Step 4 — Set up the Chrome automation profile

Scout and submit agents use headed Chrome. The multiplexer copies auth from a dedicated profile into each browser instance, so you only need to log in once.

```bash
./scripts/setup-chrome-profile.sh
```

Chrome opens with login tabs for LinkedIn, Indeed, and Upwork. Log into each, then close Chrome.

Verify the profile was saved:

```bash
ls ~/.config/chrome-automation/Default/
# Should show: Cookies, Local Storage, etc.
```

**Re-authenticating:** If sessions expire, run the script again. Close all multiplexer instances first to avoid profile lock conflicts.

**Custom profile location:** Set `CHROME_AUTOMATION_PROFILE=/your/path` before running the script, then update the path in `.mcp.json` to match.

### Step 5 — Initialize the SQLite database

```bash
python scripts/import_to_db.py
```

This creates `data/explorer.db` with the schema from `data/schema.sql`. The `explorer-db` MCP server uses this as the canonical job/contract registry.

### Step 6 — Environment variables

The setup script creates `.env` interactively. To create it manually:

```bash
cat > .env <<EOF
POSTHOG_API_KEY=your-key-here
POSTHOG_USER_NAME=your-name
POSTHOG_DISTINCT_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
EOF
```

| Variable | Required | Purpose |
|---|---|---|
| `POSTHOG_API_KEY` | Yes | Pipeline analytics — agents and pipeline script both use this |
| `POSTHOG_USER_NAME` | No | Your display name in analytics |
| `POSTHOG_DISTINCT_ID` | Auto | Unique analytics ID (generated by setup script) |
| `DEEP_SEEK_API_KEY` | No | DeepSeek model for build agents |
| `GOOGLE_API_KEY` | No | Gemini embeddings |
| `ANONYMIZED_TELEMETRY` | No | Set `false` to disable telemetry |

### Step 7 — MCP configuration

The setup script creates `.mcp.json` automatically. To create it manually:

```bash
cat > .mcp.json <<EOF
{
  "mcpServers": {
    "playwright-mux-parallel": {
      "command": "bash",
      "args": [
        "$(pwd)/scripts/start-playwright-mux.sh",
        "--max-instances=10"
      ]
    },
    "explorer-db": {
      "command": "uvx",
      "args": [
        "mcp-server-sqlite",
        "--db-path",
        "$(pwd)/data/explorer.db"
      ]
    }
  }
}
EOF
```

The `start-playwright-mux.sh` launcher resolves `$HOME` at runtime, so no hardcoded username is needed.

### Step 8 — Knowledge base

The pipeline generates tailored resumes from your personal knowledge base in `knowledge/`. See **`KNOWLEDGE_BASE.md`** for full schema reference and manual instructions.

#### Automated setup (recommended)

Drop your resume (PDF, `.txt`, or `.md`) into the `setup/` directory, then ask Claude:

```
Set up the pipeline with my resume. I'm in <City, State>. <Work authorization>.
```

The setup agent reads your resume and automatically fills `profile.yaml`, `skills.yaml`, all experience and project files, and the template headers. It generates all three bullet variants (technical/impact/leadership) for every entry. It outputs a checklist of what was filled and what still needs manual input.

#### Credentials (always manual)

```bash
cp knowledge/credentials.yaml.example knowledge/credentials.yaml
```

Fill in your ATS login credentials. The submit agent uses these when browser sessions expire. This file is gitignored — the setup agent does not touch it.

### Step 9 — Verify everything

```bash
# System dependencies
tectonic --version
google-chrome-stable --version
/usr/bin/Xvfb -help 2>&1 | head -1

# Database
python scripts/import_to_db.py

# Pipeline CLI
python scripts/pipeline status

# Multiplexer responds to MCP protocol
printf '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{"roots":{"listChanged":false}},"clientInfo":{"name":"test","version":"0.1"}},"id":1}\n{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}\n' \
  | timeout 20 node playwright-mcp/packages/playwright-mcp-multiplexer/dist/cli.js --browser=chrome --headed 2>&1 \
  | grep -o '"name":"playwright-mcp-multiplexer"'
# Expected: "name":"playwright-mcp-multiplexer"
```

Then open the project in Claude Code and confirm both MCP servers connect:

```bash
cd Mercury_Alpha_Test
claude
# Ask: "What MCP servers are available?"
```

**Important:** Claude Code only loads MCP servers on startup. After editing `.mcp.json`, restart Claude Code for the changes to take effect.

---

## Optional: activity logging

Create `.claude/settings.json` to log all tool calls to `logs/YYYY-MM-DD.jsonl`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__.*|Read|Write|Edit|Glob|Grep|Bash",
        "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/log-activity.sh" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "mcp__.*|Read|Write|Edit|Glob|Grep|Bash",
        "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/log-activity.sh" }]
      }
    ]
  }
}
```

---

## Running the pipeline

```bash
# Full pipeline: scout 10 jobs, build applications, submit them
python scripts/pipeline 10

# Step by step
python scripts/pipeline scout 15     # Find 15 jobs
python scripts/pipeline status       # Review what was found
python scripts/pipeline build        # Build applications for all scouted
python scripts/pipeline submit       # Submit all built applications

# Monitor
python scripts/pipeline watch        # Live dashboard
python scripts/pipeline follow       # Stream logs
python scripts/pipeline log          # Last 50 log lines

# Upwork freelance pipeline
python scripts/pipeline upwork 10    # Scout + propose 10 contracts
python scripts/pipeline upwork scout 5
python scripts/pipeline upwork propose
python scripts/pipeline upwork status
```

Or talk to Claude Code directly in the project directory — it orchestrates all agents and handles the pipeline conversationally.

---

## Multiplexer CLI flags reference

| Flag | Default | Description |
|---|---|---|
| `--browser` | `chromium` | Browser (`chrome`, `chromium`, `firefox`) |
| `--headed` | `false` | Show browser windows |
| `--headless` | `true` | Hide browser windows |
| `--max-instances` | `5` | Max concurrent browser instances |
| `--user-data-dir` | — | Chrome profile for pre-authenticated sessions |
| `--profile` | — | Profile name within user-data-dir |
| `--auth-dir` | `~/.pride-riot/auth/` | Directory for exported auth state files |

---

## Setup checklist

If you ran `./setup.sh`, most infrastructure items are already done. Use this to verify.

### Infrastructure
- [ ] Claude Code installed and authenticated
- [ ] `./setup.sh` completed without errors (handles all items below)
- [ ] `google-chrome-stable` installed
- [ ] `Xvfb` installed at `/usr/bin/Xvfb`
- [ ] `node` 18+ installed
- [ ] `python3` + virtual environment (`.venv/`) set up
- [ ] `tectonic` installed
- [ ] WSL display working (`$DISPLAY` set) — WSL2 only
- [ ] Submodules initialized and multiplexer built
- [ ] `.mcp.json` created (setup script uses runtime path resolution)
- [ ] Chrome profile created and logged into LinkedIn, Indeed, Upwork
- [ ] SQLite database initialized (`data/explorer.db` exists)
- [ ] `.env` created with PostHog API key
- [ ] Claude Code restarted after setup (to load MCP servers)

### Knowledge base (see KNOWLEDGE_BASE.md)
- [ ] Resume dropped into `setup/` and setup agent run
- [ ] `knowledge/credentials.yaml` filled with ATS login credentials
- [ ] `scout.md` location placeholders replaced (required before scouting)
