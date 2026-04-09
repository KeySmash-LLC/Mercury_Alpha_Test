# Project Mercury V1

An automated job application pipeline powered by Claude Code agents and Playwright MCP browser automation.

## Before use

- This is an **Alpha test** — a pre-release version of the software.
- AI can and does make mistakes. Submitted applications may contain errors.
- **By using this you accept the risk that your LinkedIn account and/or your IP may be banned by the service.**

## What it does

Mercury scouts job postings on LinkedIn/Indeed and Upwork, generates tailored resumes and cover letters using your knowledge base, and submits applications via browser automation — all orchestrated by Claude Code.

```
Scout (browser) → User Review → Build (AI + LaTeX) → User Review → Submit (browser)
```

### Pipeline stages

| Stage | Agent | Browser? | What happens |
|-------|-------|----------|--------------|
| **Scout** | Job-Scouter | Yes | Searches job boards, extracts postings, saves structured YAML |
| **Build** | Job-Application-Builder | No | Reads job + knowledge base, generates tailored resume/cover letter LaTeX, compiles PDFs |
| **Submit** | Job-Submiter | Yes | Navigates application forms, fills fields, uploads PDFs, submits |

There's also a parallel **Upwork pipeline** (Scout → Propose → Fill Form → Manual Submit).

## Requirements

- Linux (tested on Ubuntu/WSL2)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) with an Anthropic API key
- A Google Chrome-compatible display (WSLg on WSL2, or a native X11/Wayland display)
- `tmux` (optional, for background pipeline execution)

All other dependencies (Chrome, Node.js, Python, tectonic, Xvfb) are installed by the setup script.

## Quick Start

1. **Clone and set up**
   ```bash
   git clone --recursive <repo-url>
   cd Mercury_Alpha_Test
   ./setup.sh
   ```
   The setup script installs all system dependencies, builds the Playwright MCP multiplexer, creates a Python virtual environment, scaffolds configuration files, initializes the database, and walks you through Chrome profile authentication. See [ENVIRONMENT.md](ENVIRONMENT.md) for manual setup or troubleshooting.

2. **Populate your knowledge base** — see [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md) for details
   - Drop your resume (PDF/TXT/MD) into `setup/` and ask Claude to "set up the pipeline" (automated), or
   - Manually edit `knowledge/profile.yaml`, `skills.yaml`, experience and project files, and template headers
   - Fill in `knowledge/credentials.yaml` with your ATS login passwords

3. **Run the pipeline**
   ```bash
   python scripts/pipeline 10          # Scout + build + submit 10 jobs
   python scripts/pipeline scout 15    # Scout only
   python scripts/pipeline build       # Build all scouted jobs
   python scripts/pipeline submit      # Submit all built applications
   python scripts/pipeline status      # Check progress
   python scripts/pipeline watch       # Live dashboard
   ```

   Or open Claude Code in the project directory and use it conversationally.

## Project Structure

```
├── .claude/
│   ├── agents/           # Subagent instruction files (scout, build, submit, upwork-*)
│   └── hooks/            # Activity logging hook (optional)
├── data/
│   ├── schema.sql        # SQLite schema for job registry
│   ├── explorer.db       # SQLite job/contract registry (created by setup)
│   ├── jobs/             # Per-job directories (created at runtime)
│   └── contracts/        # Per-contract directories (Upwork, created at runtime)
├── knowledge/            # Your personal knowledge base (customize these!)
│   ├── profile.yaml      # Contact info, education, work auth
│   ├── skills.yaml       # Skills with proficiency levels
│   ├── credentials.yaml  # ATS login credentials (gitignored)
│   ├── experience/       # One YAML per work experience
│   └── projects/         # One YAML per project
├── scripts/
│   ├── pipeline          # CLI entry point
│   ├── build-mcp.sh      # Build the Playwright MCP multiplexer
│   ├── setup-chrome-profile.sh  # Chrome authentication setup
│   └── ...               # Analytics, import, validation scripts
├── templates/
│   ├── resume.tex        # LaTeX resume template
│   └── cover_letter.tex  # LaTeX cover letter template
├── setup.sh              # One-shot bootstrap script
├── CLAUDE.md             # Orchestrator instructions for Claude Code
├── ENVIRONMENT.md        # System/infrastructure setup guide
└── KNOWLEDGE_BASE.md     # Personal data setup: resume, skills, experience
```

## How it works

Mercury uses Claude Code as an orchestrator that spawns specialized Haiku subagents via the Task tool. Each agent has focused instructions (in `.claude/agents/`) and operates independently:

- **Scout agents** use Playwright MCP to browse job boards in headed Chrome instances
- **Build agents** read your knowledge base and generate LaTeX documents (no browser needed)
- **Submit agents** each get their own browser instance to fill and submit application forms

The Playwright MCP Multiplexer enables parallel browser automation — multiple scouts and submitters can run concurrently with isolated Chrome instances.

Job data flows through a SQLite database (`data/explorer.db`) for deduplication, and per-job YAML files in `data/jobs/<slug>/` for human-readable state.

## License

Private — KeySmash LLC
