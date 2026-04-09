# Environment Setup (macOS)

System and infrastructure setup: dependencies, Chrome profile, database, and MCP configuration.

---

## Prerequisites

Install these before anything else.

### Homebrew

If not already installed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After installing, follow the printed instructions to add Homebrew to your PATH (especially on Apple Silicon).

### Claude Code

This project is orchestrated by Claude Code. Install it first:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Requires an [Anthropic API key](https://console.anthropic.com/). On first run, `claude` will prompt you to authenticate.

### System packages

```bash
# Chrome (for browser automation)
brew install --cask google-chrome

# Node.js 18+ (for the multiplexer build and runtime)
brew install node

# Python 3 + pip (for pipeline scripts and SQLite MCP server)
brew install python3

# tectonic (LaTeX compiler for resume/cover letter PDFs)
brew install tectonic
```

> **Note:** Xvfb is not needed on macOS — Chrome runs headed natively without a virtual display.

---

## Step 1 — Clone and initialize submodules

```bash
git clone <repo-url> Project-Mercury-V1
cd Project-Mercury-V1
git submodule update --init --recursive
```

---

## Step 2 — Build the Playwright MCP Multiplexer

```bash
./scripts/build-mcp.sh
```

This initializes submodules, installs npm dependencies, builds the Playwright fork, and compiles the multiplexer TypeScript. Re-run after pulling submodule updates.

Verify the build output exists:

```bash
ls playwright-mcp/packages/playwright-mcp-multiplexer/dist/cli.js
```

---

## Step 3 — Fix the MCP config user path

`.mcp.json` ships with a hardcoded placeholder username in `--user-data-dir`. **Update it to your actual username before anything else:**

```bash
# Find the line and replace with your username
# Note: macOS sed requires an empty string after -i
sed -i '' "s|/home/electron/.config/chrome-automation|$HOME/.config/chrome-automation|g" .mcp.json
```

Or edit `.mcp.json` manually — change:
```
"--user-data-dir=/home/electron/.config/chrome-automation"
```
to:
```
"--user-data-dir=/Users/YOUR_USERNAME/.config/chrome-automation"
```

**This must be done before setting up the Chrome profile**, otherwise the multiplexer won't find the profile and browser instances will launch unauthenticated.

---

## Step 4 — Set up the Chrome automation profile

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

**Custom profile location:** Set `CHROME_AUTOMATION_PROFILE=/your/path` before running the script, then update `--user-data-dir` in `.mcp.json` to match.

---

## Step 5 — Initialize the SQLite database

```bash
pip3 install mcp-server-sqlite   # or: pipx install mcp-server-sqlite
python3 scripts/import_to_db.py
```

This creates `data/explorer.db` with the schema from `data/schema.sql`. The `explorer-db` MCP server uses this as the canonical job/contract registry.

---

## Step 6 — Environment variables

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `POSTHOG_API_KEY` | Yes | Pipeline analytics — agents and pipeline script both use this |
| `POSTHOG_USER_NAME` | No | Your display name in analytics |
| `DEEP_SEEK_API_KEY` | No | DeepSeek model for build agents |
| `GOOGLE_API_KEY` | No | Gemini embeddings |
| `ANONYMIZED_TELEMETRY` | No | Set `false` to disable telemetry |

---

## Step 7 — Knowledge base

The pipeline generates tailored resumes from your personal knowledge base in `knowledge/`. See **`KNOWLEDGE_BASE.md`** for full schema reference and manual instructions.

### Automated setup (recommended)

Drop your resume (PDF, `.txt`, or `.md`) into the `setup/` directory, then ask Claude:

```
Set up the pipeline with my resume. I'm in <City, State>. <Work authorization>.
```

The setup agent reads your resume and automatically fills `profile.yaml`, `skills.yaml`, all experience and project files, and the template headers. It generates all three bullet variants (technical/impact/leadership) for every entry. It outputs a checklist of what was filled and what still needs manual input.

### Credentials (always manual)

```bash
cp knowledge/credentials.yaml.example knowledge/credentials.yaml
```

Fill in your ATS login credentials. The submit agent uses these when browser sessions expire. This file is gitignored — the setup agent does not touch it.

---

## Step 8 — Verify everything

```bash
# System dependencies
tectonic --version
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version

# Database
python3 scripts/import_to_db.py

# Pipeline CLI
python3 scripts/pipeline status

# Multiplexer responds to MCP protocol
printf '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{"roots":{"listChanged":false}},"clientInfo":{"name":"test","version":"0.1"}},"id":1}\n{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}\n' \
  | timeout 20 node playwright-mcp/packages/playwright-mcp-multiplexer/dist/cli.js --browser=chrome --headed 2>&1 \
  | grep -o '"name":"playwright-mcp-multiplexer"'
# Expected: "name":"playwright-mcp-multiplexer"
```

Then open the project in Claude Code and confirm both MCP servers connect:

```bash
cd /path/to/Project-Mercury-V1
claude
# Ask: "What MCP servers are available?"
```

**Important:** Claude Code only loads MCP servers on startup. After editing `.mcp.json`, restart Claude Code for the changes to take effect.

---

## Step 9 — Optional: activity logging

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
python3 scripts/pipeline 10

# Step by step
python3 scripts/pipeline scout 15     # Find 15 jobs
python3 scripts/pipeline status       # Review what was found
python3 scripts/pipeline build        # Build applications for all scouted
python3 scripts/pipeline submit       # Submit all built applications

# Monitor
python3 scripts/pipeline watch        # Live dashboard
python3 scripts/pipeline follow       # Stream logs
python3 scripts/pipeline log          # Last 50 log lines

# Upwork freelance pipeline
python3 scripts/pipeline upwork 10    # Scout + propose 10 contracts
python3 scripts/pipeline upwork scout 5
python3 scripts/pipeline upwork propose
python3 scripts/pipeline upwork status
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

### Infrastructure
- [ ] Homebrew installed
- [ ] Claude Code installed and authenticated
- [ ] `google-chrome` installed (via `brew install --cask google-chrome`)
- [ ] `node` 18+ installed
- [ ] `python3` installed
- [ ] `tectonic` installed
- [ ] Submodules initialized (`git submodule update --init --recursive`)
- [ ] Multiplexer built (`./scripts/build-mcp.sh`)
- [ ] `.mcp.json` `--user-data-dir` updated to your actual username
- [ ] Chrome profile created and logged into LinkedIn, Indeed, Upwork
- [ ] SQLite database initialized (`python3 scripts/import_to_db.py`)
- [ ] `.env` created and API keys filled in
- [ ] Multiplexer responds to `tools/list` without errors
- [ ] Claude Code restarted after editing `.mcp.json`

### Knowledge base (see KNOWLEDGE_BASE.md)
- [ ] Resume dropped into `setup/` and setup agent run
- [ ] `knowledge/credentials.yaml` filled with ATS login credentials
- [ ] `scout.md` location placeholders replaced (required before scouting)
