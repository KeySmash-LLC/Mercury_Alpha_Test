#!/usr/bin/env python3
"""
Token usage and cost analysis for Explorer pipeline Claude Code sessions.

Parses JSONL conversation files from ~/.claude/projects/ to compute token
usage, cost breakdown by model, and agent type classification.

Usage:
    python scripts/analyze_token_usage.py          # Human-readable report
    python scripts/analyze_token_usage.py --json   # Machine-readable JSON
"""

import argparse
import collections
import json
import os
import pathlib
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLAUDE_PROJECTS = pathlib.Path.home() / ".claude" / "projects"

PROJECT_DIRS = [
    "-home-electron-projects-explorer-workspace-Explorer",
    "-home-electron-projects-explorer-workspace",
    "-home-electron-projects-Explorer",
]

# Per-million-token pricing
MODEL_PRICING = {
    "claude-opus-4-6": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_write": 1.00,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
}


def get_pricing(model: str) -> dict:
    """Look up pricing, falling back to opus if unknown."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Fuzzy match
    for key in MODEL_PRICING:
        if key in model or model in key:
            return MODEL_PRICING[key]
    return MODEL_PRICING["claude-opus-4-6"]


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

def extract_usage_from_file(filepath: pathlib.Path) -> list[dict]:
    """Extract all assistant usage records from a JSONL file."""
    records = []
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message", {})
                usage = msg.get("usage")
                if not usage:
                    continue
                model = msg.get("model", "unknown")
                timestamp = rec.get("timestamp", "")
                records.append({
                    "model": model,
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                    "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                    "timestamp": timestamp,
                })
    except (OSError, UnicodeDecodeError):
        pass
    return records


def classify_agent(filepath: pathlib.Path) -> str:
    """Classify a subagent file by its first user message."""
    fname = filepath.name
    if "compact" in fname:
        return "compact"

    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "user":
                    continue
                msg = rec.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            content = c["text"]
                            break
                    else:
                        content = ""
                cl = content.lower()[:600]
                if "upwork" in cl:
                    return "upwork"
                if "scout" in cl or cl.startswith("search "):
                    return "scout"
                if any(w in cl for w in ("build", "resume", "cover letter", "application builder", "generate a tailored")):
                    return "build"
                if any(w in cl for w in ("submit", "submission")):
                    return "submit"
                return "unknown"
    except (OSError, UnicodeDecodeError):
        pass
    return "unknown"


def get_first_user_content(filepath: pathlib.Path) -> str:
    """Get first user message content (for session labeling)."""
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "user":
                    continue
                msg = rec.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            return c["text"][:200]
                elif isinstance(content, str):
                    return content[:200]
                break
    except (OSError, UnicodeDecodeError):
        pass
    return ""


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

def compute_cost(records: list[dict]) -> float:
    """Compute total cost for a list of usage records."""
    total = 0.0
    for r in records:
        pricing = get_pricing(r["model"])
        total += r["input_tokens"] * pricing["input"] / 1_000_000
        total += r["output_tokens"] * pricing["output"] / 1_000_000
        total += r["cache_read_input_tokens"] * pricing["cache_read"] / 1_000_000
        total += r["cache_creation_input_tokens"] * pricing["cache_write"] / 1_000_000
    return total


def aggregate_by_model(records: list[dict]) -> dict:
    """Aggregate tokens and cost by model."""
    by_model: dict[str, dict] = {}
    for r in records:
        model = r["model"]
        if model not in by_model:
            by_model[model] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "api_calls": 0,
            }
        m = by_model[model]
        m["input_tokens"] += r["input_tokens"]
        m["output_tokens"] += r["output_tokens"]
        m["cache_creation_input_tokens"] += r["cache_creation_input_tokens"]
        m["cache_read_input_tokens"] += r["cache_read_input_tokens"]
        m["api_calls"] += 1

    for model, m in by_model.items():
        pricing = get_pricing(model)
        m["cost"] = round(
            m["input_tokens"] * pricing["input"] / 1_000_000
            + m["output_tokens"] * pricing["output"] / 1_000_000
            + m["cache_read_input_tokens"] * pricing["cache_read"] / 1_000_000
            + m["cache_creation_input_tokens"] * pricing["cache_write"] / 1_000_000,
            4,
        )
    return by_model


# ---------------------------------------------------------------------------
# Main scanning
# ---------------------------------------------------------------------------

def scan_all_sessions() -> dict:
    """Scan all project directories and return comprehensive results."""
    all_records = []
    main_records = []
    subagent_records = []

    session_costs = []  # (session_id, cost, label, project_dir)
    agent_type_stats: dict[str, dict] = collections.defaultdict(lambda: {"invocations": 0, "records": [], "cost": 0.0})
    daily_costs: dict[str, float] = collections.defaultdict(float)

    file_counts = {"main": 0, "subagent": 0, "total_size_bytes": 0}

    for proj_dir_name in PROJECT_DIRS:
        proj_path = CLAUDE_PROJECTS / proj_dir_name
        if not proj_path.exists():
            continue

        # Main session files (*.jsonl directly in project dir)
        for jsonl_file in sorted(proj_path.glob("*.jsonl")):
            file_counts["main"] += 1
            file_counts["total_size_bytes"] += jsonl_file.stat().st_size
            records = extract_usage_from_file(jsonl_file)
            all_records.extend(records)
            main_records.extend(records)

            cost = compute_cost(records)
            label = get_first_user_content(jsonl_file)
            session_id = jsonl_file.stem
            session_costs.append((session_id, cost, label, proj_dir_name))

            for r in records:
                ts = r.get("timestamp", "")
                if ts:
                    day = ts[:10]
                    pricing = get_pricing(r["model"])
                    day_cost = (
                        r["input_tokens"] * pricing["input"] / 1_000_000
                        + r["output_tokens"] * pricing["output"] / 1_000_000
                        + r["cache_read_input_tokens"] * pricing["cache_read"] / 1_000_000
                        + r["cache_creation_input_tokens"] * pricing["cache_write"] / 1_000_000
                    )
                    daily_costs[day] += day_cost

        # Subagent files (*/subagents/*.jsonl)
        for subagent_dir in sorted(proj_path.glob("*/subagents")):
            for jsonl_file in sorted(subagent_dir.glob("*.jsonl")):
                file_counts["subagent"] += 1
                file_counts["total_size_bytes"] += jsonl_file.stat().st_size
                records = extract_usage_from_file(jsonl_file)
                all_records.extend(records)
                subagent_records.extend(records)

                agent_type = classify_agent(jsonl_file)
                cost = compute_cost(records)
                agent_type_stats[agent_type]["invocations"] += 1
                agent_type_stats[agent_type]["records"].extend(records)
                agent_type_stats[agent_type]["cost"] += cost

                for r in records:
                    ts = r.get("timestamp", "")
                    if ts:
                        day = ts[:10]
                        pricing = get_pricing(r["model"])
                        day_cost = (
                            r["input_tokens"] * pricing["input"] / 1_000_000
                            + r["output_tokens"] * pricing["output"] / 1_000_000
                            + r["cache_read_input_tokens"] * pricing["cache_read"] / 1_000_000
                            + r["cache_creation_input_tokens"] * pricing["cache_write"] / 1_000_000
                        )
                        daily_costs[day] += day_cost

    # Aggregate
    total_cost = compute_cost(all_records)
    main_cost = compute_cost(main_records)
    subagent_cost = compute_cost(subagent_records)
    by_model = aggregate_by_model(all_records)

    # Agent type summary
    agent_summary = {}
    for agent_type, stats in sorted(agent_type_stats.items()):
        inv = stats["invocations"]
        cost = stats["cost"]
        agent_summary[agent_type] = {
            "invocations": inv,
            "total_cost": round(cost, 2),
            "avg_cost_per_invocation": round(cost / inv, 2) if inv > 0 else 0,
            "by_model": aggregate_by_model(stats["records"]),
        }

    # Top sessions
    session_costs.sort(key=lambda x: x[1], reverse=True)
    top_sessions = [
        {"session_id": s[0], "cost": round(s[1], 2), "label": s[3] + ": " + s[2]}
        for s in session_costs[:15]
    ]

    # Daily timeline
    daily_timeline = {day: round(cost, 2) for day, cost in sorted(daily_costs.items())}

    return {
        "generated_at": datetime.now().isoformat(),
        "file_counts": {
            "main_sessions": file_counts["main"],
            "subagent_files": file_counts["subagent"],
            "total_files": file_counts["main"] + file_counts["subagent"],
            "total_size_mb": round(file_counts["total_size_bytes"] / 1_048_576, 1),
        },
        "total_cost": round(total_cost, 2),
        "main_thread_cost": round(main_cost, 2),
        "subagent_cost": round(subagent_cost, 2),
        "total_api_calls": len(all_records),
        "main_api_calls": len(main_records),
        "subagent_api_calls": len(subagent_records),
        "by_model": {
            model: {k: v for k, v in data.items()}
            for model, data in sorted(by_model.items(), key=lambda x: -x[1].get("cost", 0))
        },
        "agent_types": agent_summary,
        "daily_timeline": daily_timeline,
        "top_sessions": top_sessions,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def fmt_tokens(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def print_report(results: dict) -> None:
    print("=" * 70)
    print("  Explorer Pipeline — Token Usage & Cost Report")
    print(f"  Generated: {results['generated_at'][:19]}")
    print("=" * 70)

    fc = results["file_counts"]
    print(f"\n--- Data Source ---")
    print(f"  Main sessions:    {fc['main_sessions']:,}")
    print(f"  Subagent files:   {fc['subagent_files']:,}")
    print(f"  Total files:      {fc['total_files']:,}")
    print(f"  Total size:       {fc['total_size_mb']:.1f} MB")

    print(f"\n--- Total Cost ---")
    print(f"  Total:            ${results['total_cost']:,.2f}")
    print(f"  Main thread:      ${results['main_thread_cost']:,.2f}  ({results['main_api_calls']:,} API calls)")
    print(f"  Subagent:         ${results['subagent_cost']:,.2f}  ({results['subagent_api_calls']:,} API calls)")
    print(f"  Total API calls:  {results['total_api_calls']:,}")

    print(f"\n--- Cost by Model ---")
    for model, data in results["by_model"].items():
        print(f"  {model}")
        print(f"    Cost:           ${data['cost']:,.2f}")
        print(f"    API calls:      {data['api_calls']:,}")
        print(f"    Input tokens:   {fmt_tokens(data['input_tokens'])}")
        print(f"    Output tokens:  {fmt_tokens(data['output_tokens'])}")
        print(f"    Cache read:     {fmt_tokens(data['cache_read_input_tokens'])}")
        print(f"    Cache write:    {fmt_tokens(data['cache_creation_input_tokens'])}")

    print(f"\n--- Orchestrator vs Subagent Split ---")
    total = results["total_cost"]
    if total > 0:
        main_pct = results["main_thread_cost"] / total * 100
        sub_pct = results["subagent_cost"] / total * 100
        print(f"  Main thread:      {main_pct:5.1f}%  (${results['main_thread_cost']:,.2f})")
        print(f"  Subagents:        {sub_pct:5.1f}%  (${results['subagent_cost']:,.2f})")

    print(f"\n--- Agent Type Breakdown ---")
    for agent_type, data in sorted(results["agent_types"].items(), key=lambda x: -x[1]["total_cost"]):
        print(f"  {agent_type:12s}  {data['invocations']:4d} invocations  ${data['total_cost']:8.2f}  avg=${data['avg_cost_per_invocation']:.2f}/invocation")

    print(f"\n--- Daily Cost Timeline ---")
    for day, cost in results["daily_timeline"].items():
        bar = "#" * max(1, int(cost / max(results["daily_timeline"].values()) * 40)) if cost > 0 else ""
        print(f"  {day}  ${cost:8.2f}  {bar}")

    print(f"\n--- Top 15 Sessions by Cost ---")
    for i, s in enumerate(results["top_sessions"], 1):
        label = s["label"][:60]
        print(f"  {i:2d}. ${s['cost']:8.2f}  {s['session_id'][:8]}  {label}")

    print("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Explorer pipeline token usage and cost")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    print("Scanning JSONL files...", file=sys.stderr)
    results = scan_all_sessions()
    print(f"Done. Processed {results['file_counts']['total_files']} files.", file=sys.stderr)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)


if __name__ == "__main__":
    main()
