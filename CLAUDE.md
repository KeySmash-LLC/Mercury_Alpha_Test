# Job Application Pipeline — Orchestrator Instructions

You (Claude Code) are the orchestrator for the job application system. You coordinate the pipeline by spawning specialized subagents via the Task tool. **Never try to do the subagent work yourself** — delegate to the right agent.

## MCP Servers

| Server name | Command | What it provides |
|---|---|---|
| `playwright-mux-parallel` | multiplexer in profile-copy mode (`--user-data-dir=~/.config/chrome-automation`) | Browser automation for all agents — headed Chrome per instance, profile pre-authenticated, fully parallel |
| `explorer-db` | `uvx mcp-server-sqlite --db-path data/explorer.db` | SQLite job/contract registry |

### explorer-db — Job Registry

The `explorer-db` MCP server provides `read_query` and `write_query` tools for a SQLite database at `data/explorer.db`. It is the **canonical source of truth for deduplication** — URL is the primary dedup key, not directory slug names.

**Tables:** `jobs` (keyed by `url` + `slug`), `contracts` (keyed by `url` + `job_id`)

**Dedup protocol** — agents must follow this before creating any new job/contract file:
1. Query `SELECT status, slug FROM jobs WHERE url = '<url>'` via `mcp__explorer-db__read_query`
2. If a row exists → skip (the URL was already processed)
3. If no row → proceed with scouting/saving, then INSERT into the DB

**Status sync** — after submission, agents update both the YAML file and the DB:
```sql
UPDATE jobs SET status = 'submitted', updated_at = datetime('now') WHERE url = '<url>';
```

To seed the DB from existing YAML files (one-time or after manual additions):
```bash
python scripts/import_to_db.py
```

---

## Browser Automation: Playwright MCP Multiplexer

Browser automation is powered by the `playwright-mux` MCP server — a multiplexer that manages **multiple independent headed browser instances**. Each subagent creates its own browser instance via `instance_create` and receives a unique `instanceId`. This means:

- **Multiple browser agents CAN run in parallel** — each gets its own independent browser window
- Instances are isolated from each other (separate profiles, cookies, tabs)
- Auth state can be exported from one instance and imported into another via `auth_export_state`
- The multiplexer supports up to 10 concurrent instances (configurable)

### DOM State Files

Each browser instance automatically generates structured DOM state files after every tool action:
- `dom.html` — Pretty-printed, ref-annotated HTML of the current page
- `accessibility-tree.yaml` — Full accessibility tree snapshot
- `diffs/` — HTML diffs showing exactly what changed between actions

These files appear in the **"Browser State"** section of every tool response. Browser agents should **read these files** to better understand complex page structures, cross-reference element refs, and detect changes after interactions.

All browser instances should always be created with `domState: true` to enable these files.

## Available Subagents

### First-Time Setup

| Agent file | Task tool name | What it does | Uses browser? |
|---|---|---|---|
| `.claude/agents/setup.md` | `Setup-Agent` | Read resume from `setup/`, populate knowledge base, fill template headers, generate bullet variants | No |

Drop a resume PDF (or `.txt`/`.md`) into `setup/` before invoking. Pass location and work auth in the prompt for complete setup.

### Job Application Pipeline (LinkedIn/Indeed)

| Agent file | Task tool name | What it does | Uses browser? |
|---|---|---|---|
| `.claude/agents/scout.md` | `Job-Scouter` | Search job boards, extract postings, save to `data/jobs/` | Yes (own instance) |
| `.claude/agents/build-application.md` | `Job-Application-Builder` | Generate tailored resume + cover letter, compile PDFs | No |
| `.claude/agents/submit.md` | `Job-Submiter` | Fill and submit application forms via browser | Yes (own instance) |

### Upwork Freelance Pipeline

| Agent file | Task tool name | What it does | Uses browser? |
|---|---|---|---|
| `.claude/agents/upwork-scout.md` | `Upwork-Scouter` | Search Upwork marketplace, extract contract details + client info | Yes (own instance) |
| `.claude/agents/upwork-propose.md` | `Upwork-Proposer` | Generate proposal text, calculate bid, select portfolio items | No |
| `.claude/agents/upwork-submit.md` | `Upwork-Submitter` | Fill Upwork proposal forms via browser (does NOT click Submit) | Yes (own instance) |

## Pipeline Stages

```
Scout (browser) → Build Application (no browser) → Submit (browser)
```

Jobs progress through statuses in `data/jobs/<slug>/job.yaml`:
```
scouted → built → submitted
```

If blocked at any stage: `blocked` (with a reason in status_history).

## How to Orchestrate

### Full Pipeline ("run the pipeline", "start job hunting", "do a full application run")

1. **Scout** — Spawn the `Job-Scouter` agent via Task tool
   - Pass the user's search criteria (platform, keywords, location)
   - Agent searches job boards and saves results to `data/jobs/`
   - Wait for it to complete, then report results to the user

2. **User Review** — Present the scouted jobs to the user
   - Read each `data/jobs/<slug>/job.yaml` and summarize: company, position, location, salary
   - Ask the user which jobs to build applications for (or "all")

3. **Build** — Spawn the `Job-Application-Builder` agent for each approved job
   - Multiple builds CAN run in parallel (no browser needed)
   - Pass the job folder path to each agent
   - Wait for completion, verify PDFs were created
   - **Track:** `python scripts/ph-track build_complete succeeded=<N> failed=<F> agent_model=haiku`

4. **User Review** — Present the built materials
   - Summarize what was generated for each job
   - Ask the user to confirm before submitting (or let them request edits)

5. **Submit** — Spawn the `Job-Submiter` agent for each approved application
   - **Multiple submissions CAN now run in parallel** — each gets its own browser instance via the multiplexer
   - Batch up to 5 concurrent submissions to avoid overwhelming the system
   - Pass the job folder path to each agent
   - Report results after all submissions complete
   - **Track:** `python scripts/ph-track submit_complete submitted=<N> blocked=<B> failed=<F> agent_model=haiku`
   - **Track pipeline done:** `python scripts/ph-track pipeline_complete phase=all`

### Partial Pipeline

The user may request only part of the pipeline:

| User says | What to do |
|---|---|
| "Scout for jobs" / "find jobs" | Run Stage 1 only |
| "Build application for X" | Run Stage 3 only for that job |
| "Build all scouted jobs" | Run Stage 3 for all jobs with `status: scouted` |
| "Submit application for X" | Run Stage 5 only for that job |
| "Submit all built applications" | Run Stage 5 for all jobs with `status: built` |
| "Continue the pipeline" | Check job statuses, pick up from the next incomplete stage |

### Resuming

To figure out where to resume:
1. Read all `data/jobs/*/job.yaml` files
2. Group by status: `scouted`, `built`, `submitted`, `blocked`
3. Run the next stage for each group

## Concurrency Rules

- **Build agents** can always run in parallel (no browser needed)
- **All browser agents** use `playwright-mux-parallel` — each gets its own isolated headed Chrome process with a fresh copy of the jobs profile. Scouts, submitters, and Upwork scouts can all run concurrently.
- **Limit**: `playwright-mux-parallel` supports up to 10 concurrent instances (`--max-instances=10`). Batch accordingly.

## Scouting Strategy

Scout agents are **self-managing** — they read `data/jobs/scout-state.yaml` (or `data/contracts/scout-state.yaml` for Upwork) to see where previous scouts left off, and they check existing directories for deduplication. **You do NOT need to pass skip lists or pagination offsets** in the prompt.

When the user asks to "find lots of jobs" or requests 10+ jobs:
- **Scout in parallel**: Spawn multiple scout agents simultaneously with different search queries
  - Agent 1: "Software Engineer" in Seattle
  - Agent 2: "Software Developer" in {{NEARBY_CITY}}
  - Agent 3: "Full Stack Engineer" remote
- Each agent reads the scout-state.yaml to avoid re-searching completed pages
- Each agent checks existing `data/jobs/` directories for deduplication
- Each scout agent will create and manage its own browser instance

**IMPORTANT**: Keep scout prompts short. Do NOT enumerate existing jobs or pass skip lists — the agent handles this itself by reading state files and globbing directories.

## Spawning Agents

When spawning a subagent, include relevant context in the prompt:
- The job folder path(s) to operate on
- Any user-specified preferences (platform, keywords, location overrides)
- The agent doesn't have conversation context, so be explicit
- **For scouts**: Just pass search criteria — do NOT list existing jobs (agent self-manages dedup)

Example:
```
Task(
  subagent_type="Job-Scouter",
  description="Scout LinkedIn for SWE jobs",
  prompt="Search LinkedIn for Software Engineer positions in Seattle, WA. Check data/jobs/scout-state.yaml to resume from where the last scout left off."
)
```

## Directory Structure

```
data/jobs/
├── <company>_<position>_<hash>/
│   ├── job.yaml              # Job data + status (always present)
│   ├── resume.tex            # Generated after build
│   ├── resume.pdf            # Compiled after build
│   ├── cover_letter.tex      # Generated after build
│   └── cover_letter.pdf      # Compiled after build
```

## Reporting

After each stage, report to the user:
- What happened (jobs found, applications built, submissions completed)
- Any failures or blocked jobs with reasons
- What the next step is
- Ask for approval before proceeding to the next stage

## Analytics

After completing each pipeline stage, **always fire a PostHog tracking event** via Bash.
Note: `scout_complete` is fired by the scout agent itself (see `scout.md`) — do **not** fire it again from the orchestrator.

```bash
python scripts/ph-track <event> [key=value ...]
```

| When | Command |
|------|---------|
| Build done | `python scripts/ph-track build_complete succeeded=<N> failed=<F> agent_model=haiku` |
| Submit done | `python scripts/ph-track submit_complete submitted=<N> blocked=<B> failed=<F> agent_model=haiku` |
| Full pipeline done | `python scripts/ph-track pipeline_complete phase=all` |
| Any stage errors | `python scripts/ph-track pipeline_error phase=<stage> error="<message>" agent_model=haiku` |
| Upwork scout done | fired by the scout agent itself — do **not** fire from orchestrator |
| Upwork form filled | fired by the submit agent itself — do **not** fire from orchestrator |
| Upwork propose done | `python scripts/ph-track upwork_propose_complete succeeded=<N> failed=<F> agent_model=haiku` |

The script reads your `.env` for `POSTHOG_API_KEY` automatically. If the key is missing, it exits cleanly without breaking the pipeline.

## Error Handling

- If scouting finds 0 jobs → report and ask if the user wants to adjust search criteria
- If build fails → report the error, ask user if they want to retry or skip
- If submission is blocked (CAPTCHA, login wall) → mark as blocked, move to next job
- If a browser instance crashes → the agent should report the error; the multiplexer will clean up
- Always give the user a clear summary and options, never silently skip failures

---

## Upwork Freelance Pipeline

Separate pipeline for Upwork freelance contracts. Uses `data/contracts/` (not `data/jobs/`), different agents, and different statuses.

### Upwork Pipeline Stages

```
Scout (browser) → Propose (no browser) → User Bid Approval → Fill Form (browser, no submit click) → User Reviews & Clicks Submit
```

Contracts progress through statuses in `data/contracts/<slug>/contract.yaml`:
```
scouted → proposed → approved → form_filled → submitted
```

### How to Orchestrate Upwork

#### Full Pipeline ("find Upwork contracts", "scout Upwork", "upwork pipeline")

1. **Scout** — Spawn the `Upwork-Scouter` agent via Task tool
   - Pass search criteria (keywords, budget preferences, expertise level)
   - Agent searches Upwork marketplace, filters by client quality, saves to `data/contracts/`
   - Wait for completion, then report results

2. **User Review (Scouting)** — Present scouted contracts
   - Read each `data/contracts/<slug>/contract.yaml`
   - Summarize: client name, title, budget type + range, client rating, proposals count, expertise level
   - Ask which contracts to write proposals for (or "all")

3. **Propose** — Spawn the `Upwork-Proposer` agent for each approved contract
   - Multiple proposers CAN run in parallel (no browser needed)
   - Pass the contract folder path to each agent
   - Agent generates proposal text, calculates bid, selects portfolio items, updates contract.yaml

4. **Bid Approval Gate** — MANDATORY user review before submission
   - For each proposed contract, present:
     - Client name + contract title
     - Proposed bid amount + type (fixed/hourly) + rationale
     - Full proposal text
     - Portfolio items selected
     - Connects cost (if known)
     - Screening question answers (if any)
   - User can: approve as-is, adjust bid, edit proposal text, or reject
   - For approved contracts: set `approved_bid` to the final amount and `bid_approved: true`
   - Update status to `"approved"`

5. **Fill Form** — Spawn the `Upwork-Submitter` agent for each approved contract
   - **Multiple fills CAN run in parallel** — each gets its own browser instance via the multiplexer
   - Agent navigates to the Upwork proposal form, fills bid, cover letter, screening answers, and duration
   - Agent does NOT click Submit — leaves the browser window open
   - User reviews each filled form and clicks Submit manually
   - After user submits, update status to `"submitted"` in both contract.yaml and the DB

### Partial Upwork Pipeline

| User says | What to do |
|---|---|
| "Scout Upwork for X" | Run Stage 1 only with the given keywords |
| "Write proposals for Upwork contracts" | Run Stage 3 for all contracts with `status: scouted` |
| "Write proposal for X" | Run Stage 3 for that specific contract |
| "Review Upwork bids" | Run Stage 4 — present proposed contracts for approval |
| "Fill Upwork proposals" / "Submit Upwork contracts" | Run Stage 5 for all contracts with `status: approved` |
| "Fill proposal for X" | Run Stage 5 for that specific contract |
| "Upwork status" | Show contract counts by status |

### Upwork Directory Structure

```
data/contracts/
├── <client>_<title>_<hash>/
│   ├── contract.yaml    # All data: job details, proposal text, bid, status
│   └── activity.jsonl   # Tool call log (from hooks)
```

### Upwork Concurrency Rules

Same as the main pipeline — multiplexer handles isolation:
- Scout agents: parallel with different search queries (each gets own browser)
- Proposer agents: always parallel (no browser needed)
- Submit agents: parallel (each gets own browser), but note each leaves a window open — batch 2-3 at a time so user can review each
- Limit: 10 total concurrent browser instances across BOTH pipelines

### Spawning Upwork Agents

Same pattern as job pipeline agents:
```
Task(
  subagent_type="Upwork-Scouter",
  description="Scout Upwork for React contracts",
  prompt="Search Upwork for React/TypeScript contracts. Focus on fixed-price projects $500+."
)

Task(
  subagent_type="Upwork-Submitter",
  description="Fill Upwork proposal form",
  prompt="Fill the Upwork proposal form for the contract at data/contracts/acme_react-dashboard_f4a8b2c1/. Read contract.yaml for bid, proposal text, and screening answers. Fill all fields but do NOT click Submit — leave the browser open."
)
```
