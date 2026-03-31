#!/usr/bin/env python3
"""
Per-subagent invocation cost analysis with model transition tracking.

Analyzes every individual subagent JSONL file, computes its total cost,
identifies the dominant model, and shows how model switches affected cost.

Usage:
    python scripts/analyze_subagent_costs.py          # Human-readable report
    python scripts/analyze_subagent_costs.py --json   # Machine-readable JSON
"""

import argparse
import collections
import json
import pathlib
import statistics
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

MODEL_PRICING = {
    "claude-opus-4-6": {
        "input": 15.0, "output": 75.0,
        "cache_read": 1.50, "cache_write": 18.75,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80, "output": 4.0,
        "cache_read": 0.08, "cache_write": 1.00,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0, "output": 15.0,
        "cache_read": 0.30, "cache_write": 3.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.0, "output": 15.0,
        "cache_read": 0.30, "cache_write": 3.75,
    },
}

MODEL_SHORT = {
    "claude-opus-4-6": "opus",
    "claude-haiku-4-5-20251001": "haiku",
    "claude-sonnet-4-5-20250929": "sonnet-4.5",
    "claude-sonnet-4-6": "sonnet-4.6",
    "<synthetic>": "synthetic",
}


def get_pricing(model: str) -> dict:
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    for key in MODEL_PRICING:
        if key in model or model in key:
            return MODEL_PRICING[key]
    return MODEL_PRICING["claude-opus-4-6"]


def short_model(model: str) -> str:
    return MODEL_SHORT.get(model, model)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_agent(filepath: pathlib.Path) -> str:
    if "compact" in filepath.name:
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
                if any(w in cl for w in (
                    "build", "resume", "cover letter",
                    "application builder", "generate a tailored",
                )):
                    return "build"
                if any(w in cl for w in ("submit", "submission")):
                    return "submit"
                return "unknown"
    except (OSError, UnicodeDecodeError):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Per-invocation analysis
# ---------------------------------------------------------------------------

def analyze_invocation(filepath: pathlib.Path) -> dict:
    """Compute cost for a single subagent invocation file."""
    model_costs: dict[str, float] = collections.defaultdict(float)
    model_calls: dict[str, int] = collections.defaultdict(int)
    model_tokens: dict[str, dict] = collections.defaultdict(
        lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    )
    first_date = None
    total_cost = 0.0

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
                ts = rec.get("timestamp", "")
                if ts and not first_date:
                    first_date = ts[:10]

                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cr = usage.get("cache_read_input_tokens", 0)
                cw = usage.get("cache_creation_input_tokens", 0)

                pricing = get_pricing(model)
                cost = (
                    inp * pricing["input"] / 1e6
                    + out * pricing["output"] / 1e6
                    + cr * pricing["cache_read"] / 1e6
                    + cw * pricing["cache_write"] / 1e6
                )
                model_costs[model] += cost
                model_calls[model] += 1
                model_tokens[model]["input"] += inp
                model_tokens[model]["output"] += out
                model_tokens[model]["cache_read"] += cr
                model_tokens[model]["cache_write"] += cw
                total_cost += cost
    except (OSError, UnicodeDecodeError):
        pass

    dominant = max(model_calls, key=model_calls.get) if model_calls else "unknown"

    return {
        "file": str(filepath),
        "total_cost": total_cost,
        "dominant_model": dominant,
        "model_costs": dict(model_costs),
        "model_calls": dict(model_calls),
        "model_tokens": {k: dict(v) for k, v in model_tokens.items()},
        "date": first_date or "unknown",
        "total_calls": sum(model_calls.values()),
    }


# ---------------------------------------------------------------------------
# Counterfactual: recompute cost as if all tokens were on a target model
# ---------------------------------------------------------------------------

def recompute_as_model(inv: dict, target_model: str) -> float:
    """Recompute an invocation's cost as if all tokens ran on target_model."""
    pricing = get_pricing(target_model)
    total = 0.0
    for model, tokens in inv["model_tokens"].items():
        total += (
            tokens["input"] * pricing["input"] / 1e6
            + tokens["output"] * pricing["output"] / 1e6
            + tokens["cache_read"] * pricing["cache_read"] / 1e6
            + tokens["cache_write"] * pricing["cache_write"] / 1e6
        )
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def scan_all() -> dict:
    agent_invocations: dict[str, list[dict]] = collections.defaultdict(list)

    for proj_dir_name in PROJECT_DIRS:
        proj_path = CLAUDE_PROJECTS / proj_dir_name
        if not proj_path.exists():
            continue
        for subagent_dir in sorted(proj_path.glob("*/subagents")):
            for jsonl_file in sorted(subagent_dir.glob("*.jsonl")):
                agent_type = classify_agent(jsonl_file)
                inv = analyze_invocation(jsonl_file)
                if inv["total_calls"] > 0:
                    agent_invocations[agent_type].append(inv)

    results = {}
    for agent_type in ("scout", "build", "submit", "upwork", "compact", "unknown"):
        invocations = agent_invocations.get(agent_type, [])
        if not invocations:
            continue

        # Group by dominant model
        by_model: dict[str, list[dict]] = collections.defaultdict(list)
        for inv in invocations:
            by_model[inv["dominant_model"]].append(inv)

        model_stats = {}
        for model in sorted(by_model, key=lambda m: -sum(i["total_cost"] for i in by_model[m])):
            invs = by_model[model]
            costs = [i["total_cost"] for i in invs]
            dates = sorted(set(i["date"] for i in invs if i["date"] != "unknown"))
            model_stats[model] = {
                "invocations": len(invs),
                "total_cost": round(sum(costs), 2),
                "avg_cost": round(statistics.mean(costs), 2),
                "median_cost": round(statistics.median(costs), 2),
                "min_cost": round(min(costs), 2),
                "max_cost": round(max(costs), 2),
                "p25_cost": round(sorted(costs)[len(costs) // 4], 2) if len(costs) >= 4 else round(min(costs), 2),
                "p75_cost": round(sorted(costs)[3 * len(costs) // 4], 2) if len(costs) >= 4 else round(max(costs), 2),
                "date_range": [dates[0], dates[-1]] if dates else [],
            }

        # Daily model transition
        daily: dict[str, dict[str, list[float]]] = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )
        for inv in invocations:
            if inv["date"] != "unknown":
                daily[inv["date"]][inv["dominant_model"]].append(inv["total_cost"])

        daily_transition = {}
        for date in sorted(daily):
            day_data = {}
            for model, costs in sorted(daily[date].items()):
                day_data[model] = {
                    "count": len(costs),
                    "avg_cost": round(statistics.mean(costs), 2),
                    "total_cost": round(sum(costs), 2),
                }
            daily_transition[date] = day_data

        # Counterfactual: what if everything was haiku?
        actual_total = sum(i["total_cost"] for i in invocations)
        haiku_total = sum(recompute_as_model(i, "claude-haiku-4-5-20251001") for i in invocations)
        opus_total = sum(recompute_as_model(i, "claude-opus-4-6") for i in invocations)

        results[agent_type] = {
            "total_invocations": len(invocations),
            "actual_total_cost": round(actual_total, 2),
            "by_model": model_stats,
            "daily_transition": daily_transition,
            "counterfactual": {
                "all_haiku": {
                    "total_cost": round(haiku_total, 2),
                    "avg_per_inv": round(haiku_total / len(invocations), 2),
                    "savings_vs_actual": round(actual_total - haiku_total, 2),
                },
                "all_opus": {
                    "total_cost": round(opus_total, 2),
                    "avg_per_inv": round(opus_total / len(invocations), 2),
                },
            },
        }

    # Grand totals
    all_actual = sum(r["actual_total_cost"] for r in results.values())
    all_haiku = sum(r["counterfactual"]["all_haiku"]["total_cost"] for r in results.values())
    all_opus = sum(r["counterfactual"]["all_opus"]["total_cost"] for r in results.values())

    return {
        "generated_at": datetime.now().isoformat(),
        "agents": results,
        "grand_total": {
            "actual": round(all_actual, 2),
            "if_all_haiku": round(all_haiku, 2),
            "if_all_opus": round(all_opus, 2),
            "savings_with_haiku": round(all_actual - all_haiku, 2),
        },
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def print_report(data: dict) -> None:
    print("=" * 74)
    print("  Subagent Per-Invocation Cost Analysis")
    print(f"  Generated: {data['generated_at'][:19]}")
    print("=" * 74)

    for agent_type, info in data["agents"].items():
        print(f"\n{'─' * 74}")
        print(f"  {agent_type.upper()} — {info['total_invocations']} invocations, ${info['actual_total_cost']:,.2f} total")
        print(f"{'─' * 74}")

        # Per-model stats
        print(f"\n  {'Model':<22s} {'Inv':>5s} {'Total':>10s} {'Avg':>8s} {'Median':>8s} {'P25':>8s} {'P75':>8s} {'Min':>8s} {'Max':>8s}")
        print(f"  {'─'*22} {'─'*5} {'─'*10} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        for model, stats in info["by_model"].items():
            print(
                f"  {short_model(model):<22s}"
                f" {stats['invocations']:5d}"
                f" ${stats['total_cost']:>8,.2f}"
                f" ${stats['avg_cost']:>6.2f}"
                f" ${stats['median_cost']:>6.2f}"
                f" ${stats['p25_cost']:>6.2f}"
                f" ${stats['p75_cost']:>6.2f}"
                f" ${stats['min_cost']:>6.2f}"
                f" ${stats['max_cost']:>6.2f}"
            )

        # Counterfactual
        cf = info["counterfactual"]
        print(f"\n  Counterfactual:")
        print(f"    If ALL haiku:  ${cf['all_haiku']['total_cost']:>8,.2f}  (avg ${cf['all_haiku']['avg_per_inv']:.2f}/inv)  savings: ${cf['all_haiku']['savings_vs_actual']:>8,.2f}")
        print(f"    If ALL opus:   ${cf['all_opus']['total_cost']:>8,.2f}  (avg ${cf['all_opus']['avg_per_inv']:.2f}/inv)")

        # Daily transition
        print(f"\n  Daily model usage:")
        print(f"  {'Date':<12s}", end="")
        all_models = sorted(set(
            m for day_data in info["daily_transition"].values()
            for m in day_data
        ))
        for m in all_models:
            print(f"  {short_model(m):>20s}", end="")
        print()

        for date, day_data in sorted(info["daily_transition"].items()):
            print(f"  {date:<12s}", end="")
            for m in all_models:
                if m in day_data:
                    d = day_data[m]
                    print(f"  {d['count']:>3d} x ${d['avg_cost']:<6.2f}     ", end="")
                else:
                    print(f"  {'—':>20s}", end="")
            print()

    # Grand summary
    gt = data["grand_total"]
    print(f"\n{'=' * 74}")
    print(f"  GRAND TOTAL (all subagents)")
    print(f"{'=' * 74}")
    print(f"  Actual total:       ${gt['actual']:>10,.2f}")
    print(f"  If all Haiku:       ${gt['if_all_haiku']:>10,.2f}")
    print(f"  If all Opus:        ${gt['if_all_opus']:>10,.2f}")
    print(f"  Savings with Haiku: ${gt['savings_with_haiku']:>10,.2f}  ({gt['savings_with_haiku'] / gt['actual'] * 100:.1f}%)")
    print(f"{'=' * 74}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze per-subagent invocation costs")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    print("Scanning subagent JSONL files...", file=sys.stderr)
    data = scan_all()
    total_invs = sum(a["total_invocations"] for a in data["agents"].values())
    print(f"Done. Analyzed {total_invs} invocations.", file=sys.stderr)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_report(data)


if __name__ == "__main__":
    main()
