# Project Mercury V1

An automated job application pipeline powered by Claude Code agents and Playwright MCP browser automation.

# BEFORE USE:

- Remember, this is an Alpha test, a pre-release version of the software.
- Install Google Chrome, sign in with a valid Google account, and (temporarily) disable adblockers.
- Have an active subscription to Claude. The lowest package at $20/month is sufficient but will limit the number of applications that can be filled.
- AI can and does make mistakes, submitted applications may contain these mistakes.

# By using this you accept the risk that your LinkedIn account and/or your IP may be banned by the service.

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

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) with an Anthropic API key
- [tectonic](https://tectonic-typesetting.github.io/) for LaTeX compilation
- Google Chrome (`google-chrome-stable`)
- Python 3.12+ with `pyyaml` and `requests`
- Node.js 18+ and npm (for building the bundled Playwright MCP multiplexer)
- `tmux` (optional, for background pipeline execution)

## Quick Start

1. **Clone and build**
   ```bash
   git clone --recursive https://github.com/KeySmash-LLC/Project-Mercury-V1.git
   cd Project-Mercury-V1
   ./scripts/build-mcp.sh          # Build the bundled Playwright MCP multiplexer
   pip install mcp-server-sqlite   # Install the SQLite MCP server
   python scripts/import_to_db.py  # Initialize the job database
   cp .env.example .env
   cp knowledge/credentials.yaml.example knowledge/credentials.yaml
   ```

   MCP servers are workspace-local — `.claude/mcp.json` is pre-configured. No global setup needed.

2. **Set up Chrome profile** — log into job boards once so agents can reuse sessions
   ```bash
   ./scripts/setup-chrome-profile.sh
   ```
   This opens Chrome with a dedicated automation profile. Log into LinkedIn, Indeed, Upwork, then close Chrome. The multiplexer copies auth from this profile for every browser instance.

3. **Populate your knowledge base** — see [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md) for details
   - Drop your resume into `setup/` and ask Claude to "set up the pipeline" (automated), or
   - Manually edit `knowledge/profile.yaml`, `skills.yaml`, experience and project files, and template headers

4. **Initialize the database**
   ```bash
   python scripts/import_to_db.py
   ```

5. **Run the pipeline**
   ```bash
   python scripts/pipeline 10          # Scout + build + submit 10 jobs
   python scripts/pipeline scout 15    # Scout only
   python scripts/pipeline build       # Build all scouted jobs
   python scripts/pipeline submit      # Submit all built applications
   python scripts/pipeline status      # Check progress
   python scripts/pipeline watch       # Live dashboard
   ```

## Project Structure

```
├── .claude/
│   ├── agents/           # Subagent instruction files (scout, build, submit, upwork-*)
│   └── hooks/            # Activity logging hook
├── data/
│   ├── schema.sql        # SQLite schema for job registry
│   ├── jobs/             # Per-job directories (created at runtime)
│   └── contracts/        # Per-contract directories (Upwork, created at runtime)
├── docs/                 # Pipeline specs and design docs
├── knowledge/            # Your personal knowledge base (customize these!)
│   ├── profile.yaml      # Contact info, education, work auth
│   ├── skills.yaml       # Skills with proficiency levels
│   ├── credentials.yaml  # ATS login credentials (gitignored)
│   ├── experience/       # One YAML per work experience
│   └── projects/         # One YAML per project
├── scripts/
│   └── pipeline          # CLI entry point
├── templates/
│   ├── resume.tex        # LaTeX resume template
│   └── cover_letter.tex  # LaTeX cover letter template
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
