#!/usr/bin/env python3
"""
Pipeline data validation script: cross-validates SQLite DB, YAML files,
and filesystem artifacts. Reports mismatches and computes pipeline metrics.

Usage:
    python scripts/validate_pipeline.py          # Human-readable report
    python scripts/validate_pipeline.py --json   # Machine-readable JSON
"""

import argparse
import collections
import json
import pathlib
import re
import sqlite3
import sys
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = pathlib.Path(__file__).parent
EXPLORER_DIR = SCRIPT_DIR.parent
DB_PATH = EXPLORER_DIR / "data" / "explorer.db"
JOBS_DIR = EXPLORER_DIR / "data" / "jobs"
CONTRACTS_DIR = EXPLORER_DIR / "data" / "contracts"

MALFORMED_SLUG_RE = re.compile(r"[ &;|]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_yaml(path: pathlib.Path) -> dict | None:
    try:
        return yaml.safe_load(path.read_text())
    except Exception:
        return None


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def extract_block_reason(data: dict) -> str:
    """Extract block reason from status_history."""
    for entry in reversed(data.get("status_history", [])):
        if entry.get("status") == "blocked":
            note = entry.get("note", "unknown")
            return note
    return "unknown"


def classify_block_reason(note: str) -> str:
    """Categorize block reasons into buckets."""
    note_lower = note.lower()
    if any(w in note_lower for w in ["captcha", "recaptcha"]):
        return "CAPTCHA"
    if any(w in note_lower for w in ["login", "sign in", "sign-in", "authentication"]):
        return "Login required"
    if any(w in note_lower for w in ["sms", "phone", "otp", "verification code", "verify"]):
        return "Phone/SMS verification"
    if any(w in note_lower for w in ["workday", "taleo", "icims", "greenhouse", "lever", "ashby"]):
        return "ATS redirect"
    if any(w in note_lower for w in ["closed", "expired", "no longer", "removed"]):
        return "Listing closed/expired"
    if any(w in note_lower for w in ["security clearance", "clearance", "citizenship", "us citizen"]):
        return "Eligibility requirement"
    if any(w in note_lower for w in ["timeout", "timed out", "crash"]):
        return "Technical failure"
    if any(w in note_lower for w in ["redirect", "external", "another site", "different site"]):
        return "External redirect"
    if any(w in note_lower for w in ["account", "create account", "register"]):
        return "Account creation required"
    if any(w in note_lower for w in ["dropdown", "could not", "unable", "failed", "error"]):
        return "Form interaction failure"
    return "Other"


def detect_platform(data: dict) -> str:
    """Detect job source platform from YAML data."""
    source = (data.get("source") or "").lower()
    if source:
        return source

    url = data.get("url") or ""
    if "linkedin.com" in url:
        return "linkedin"
    if "indeed.com" in url:
        return "indeed"
    if "upwork.com" in url:
        return "upwork"
    return "other"


def detect_remote(data: dict) -> str:
    """Normalize remote/onsite/hybrid."""
    remote = (data.get("remote") or "").lower().strip()
    if remote in ("remote", "yes", "true"):
        return "remote"
    if remote in ("onsite", "on-site", "no", "false"):
        return "onsite"
    if remote in ("hybrid",):
        return "hybrid"
    if remote:
        return remote
    return "unknown"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_job_status_counts(yaml_jobs: dict[str, dict], db_conn: sqlite3.Connection) -> dict:
    """Compare status counts between YAML files and DB."""
    yaml_statuses = collections.Counter()
    for slug, data in yaml_jobs.items():
        yaml_statuses[data.get("status", "unknown")] += 1

    db_statuses = collections.Counter()
    for row in db_conn.execute("SELECT status, COUNT(*) as n FROM jobs GROUP BY status"):
        db_statuses[row["status"]] = row["n"]

    all_statuses = sorted(set(yaml_statuses) | set(db_statuses))
    mismatches = []
    for s in all_statuses:
        y = yaml_statuses.get(s, 0)
        d = db_statuses.get(s, 0)
        if y != d:
            mismatches.append({"status": s, "yaml": y, "db": d})

    return {
        "yaml_counts": dict(yaml_statuses),
        "db_counts": dict(db_statuses),
        "mismatches": mismatches,
        "yaml_total": sum(yaml_statuses.values()),
        "db_total": sum(db_statuses.values()),
        "ok": len(mismatches) == 0,
    }


def check_contract_status_counts(yaml_contracts: dict[str, dict], db_conn: sqlite3.Connection) -> dict:
    yaml_statuses = collections.Counter()
    for slug, data in yaml_contracts.items():
        yaml_statuses[data.get("status", "unknown")] += 1

    db_statuses = collections.Counter()
    for row in db_conn.execute("SELECT status, COUNT(*) as n FROM contracts GROUP BY status"):
        db_statuses[row["status"]] = row["n"]

    all_statuses = sorted(set(yaml_statuses) | set(db_statuses))
    mismatches = []
    for s in all_statuses:
        y = yaml_statuses.get(s, 0)
        d = db_statuses.get(s, 0)
        if y != d:
            mismatches.append({"status": s, "yaml": y, "db": d})

    return {
        "yaml_counts": dict(yaml_statuses),
        "db_counts": dict(db_statuses),
        "mismatches": mismatches,
        "yaml_total": sum(yaml_statuses.values()),
        "db_total": sum(db_statuses.values()),
        "ok": len(mismatches) == 0,
    }


def check_slug_sync(yaml_slugs: set[str], db_conn: sqlite3.Connection, table: str) -> dict:
    """Find slugs on disk but not in DB, and vice versa."""
    db_slugs = set()
    for row in db_conn.execute(f"SELECT slug FROM {table}"):
        db_slugs.add(row["slug"])

    disk_only = sorted(yaml_slugs - db_slugs)
    db_only = sorted(db_slugs - yaml_slugs)
    return {
        "disk_only": disk_only,
        "db_only": db_only,
        "disk_count": len(yaml_slugs),
        "db_count": len(db_slugs),
        "ok": len(disk_only) == 0 and len(db_only) == 0,
    }


def check_artifacts(yaml_jobs: dict[str, dict]) -> dict:
    """Check that built/submitted jobs have resume.pdf and cover_letter.pdf."""
    missing = []
    checked = 0
    for slug, data in yaml_jobs.items():
        status = data.get("status", "")
        if status not in ("built", "submitted"):
            continue
        checked += 1
        job_dir = JOBS_DIR / slug
        missing_files = []
        for fname in ("resume.pdf", "cover_letter.pdf"):
            if not (job_dir / fname).exists():
                missing_files.append(fname)
        if missing_files:
            missing.append({"slug": slug, "status": status, "missing": missing_files})

    return {
        "checked": checked,
        "missing_count": len(missing),
        "missing": missing,
        "ok": len(missing) == 0,
    }


def check_duplicate_urls(yaml_jobs: dict[str, dict]) -> dict:
    """Detect duplicate URLs across YAML files."""
    url_to_slugs: dict[str, list[str]] = collections.defaultdict(list)
    for slug, data in yaml_jobs.items():
        url = data.get("url", "")
        if url:
            url_to_slugs[url].append(slug)

    duplicates = {url: slugs for url, slugs in url_to_slugs.items() if len(slugs) > 1}
    return {
        "unique_urls": len(url_to_slugs),
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
        "ok": len(duplicates) == 0,
    }


def check_platform_breakdown(yaml_jobs: dict[str, dict]) -> dict:
    """Platform breakdown with per-platform status counts."""
    platform_status: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for slug, data in yaml_jobs.items():
        platform = detect_platform(data)
        status = data.get("status", "unknown")
        platform_status[platform][status] += 1

    result = {}
    for platform in sorted(platform_status):
        counts = dict(platform_status[platform])
        total = sum(counts.values())
        submitted = counts.get("submitted", 0)
        result[platform] = {
            "total": total,
            "statuses": counts,
            "submit_rate": round(submitted / total * 100, 1) if total > 0 else 0,
        }
    return result


def check_block_reasons(yaml_jobs: dict[str, dict]) -> dict:
    """Categorize block reasons."""
    categories: dict[str, list[dict]] = collections.defaultdict(list)
    for slug, data in yaml_jobs.items():
        if data.get("status") != "blocked":
            continue
        note = extract_block_reason(data)
        category = classify_block_reason(note)
        categories[category].append({"slug": slug, "note": note})

    summary = {cat: len(items) for cat, items in categories.items()}
    return {
        "total_blocked": sum(summary.values()),
        "categories": summary,
        "details": {cat: items for cat, items in categories.items()},
    }


def check_timeline(yaml_jobs: dict[str, dict]) -> dict:
    """Group jobs by date_scouted and track status transitions."""
    by_date: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for slug, data in yaml_jobs.items():
        date = data.get("date_scouted", "unknown")
        status = data.get("status", "unknown")
        by_date[date][status] += 1

    result = {}
    for date in sorted(by_date):
        counts = dict(by_date[date])
        result[date] = {"total": sum(counts.values()), "statuses": counts}
    return result


def check_company_distribution(yaml_jobs: dict[str, dict]) -> dict:
    """Company distribution with per-company success rates."""
    company_status: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for slug, data in yaml_jobs.items():
        company = data.get("company", "unknown")
        status = data.get("status", "unknown")
        company_status[company][status] += 1

    result = {}
    for company in sorted(company_status):
        counts = dict(company_status[company])
        total = sum(counts.values())
        submitted = counts.get("submitted", 0)
        result[company] = {
            "total": total,
            "statuses": counts,
            "submit_rate": round(submitted / total * 100, 1) if total > 0 else 0,
        }
    return {
        "unique_companies": len(result),
        "companies": result,
        "top_10_by_volume": sorted(result.items(), key=lambda x: x[1]["total"], reverse=True)[:10],
    }


def check_remote_breakdown(yaml_jobs: dict[str, dict]) -> dict:
    """Remote/onsite/hybrid breakdown."""
    remote_status: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for slug, data in yaml_jobs.items():
        remote = detect_remote(data)
        status = data.get("status", "unknown")
        remote_status[remote][status] += 1

    result = {}
    for remote_type in sorted(remote_status):
        counts = dict(remote_status[remote_type])
        total = sum(counts.values())
        result[remote_type] = {"total": total, "statuses": counts}
    return result


# ---------------------------------------------------------------------------
# Load all data
# ---------------------------------------------------------------------------

def load_all_jobs() -> dict[str, dict]:
    jobs = {}
    if not JOBS_DIR.exists():
        return jobs
    for job_dir in sorted(JOBS_DIR.iterdir()):
        if not job_dir.is_dir():
            continue
        slug = job_dir.name
        if MALFORMED_SLUG_RE.search(slug):
            continue
        yaml_path = job_dir / "job.yaml"
        if not yaml_path.exists():
            continue
        data = load_yaml(yaml_path)
        if data:
            jobs[slug] = data
    return jobs


def load_all_contracts() -> dict[str, dict]:
    contracts = {}
    if not CONTRACTS_DIR.exists():
        return contracts
    for contract_dir in sorted(CONTRACTS_DIR.iterdir()):
        if not contract_dir.is_dir():
            continue
        slug = contract_dir.name
        if MALFORMED_SLUG_RE.search(slug):
            continue
        yaml_path = contract_dir / "contract.yaml"
        if not yaml_path.exists():
            continue
        data = load_yaml(yaml_path)
        if data:
            contracts[slug] = data
    return contracts


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def indicator(ok: bool) -> str:
    if ok:
        return "PASS"
    return "FAIL"


def warn_indicator(count: int) -> str:
    if count == 0:
        return "PASS"
    return "WARN"


def print_report(results: dict) -> None:
    print("=" * 70)
    print("  Explorer Pipeline Validation Report")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. Job status counts
    jsc = results["job_status_counts"]
    print(f"\n[{indicator(jsc['ok'])}] Job Status Counts (YAML vs DB)")
    print(f"  YAML total: {jsc['yaml_total']}  |  DB total: {jsc['db_total']}")
    print("  Status breakdown (YAML):")
    for s, n in sorted(jsc["yaml_counts"].items(), key=lambda x: -x[1]):
        db_n = jsc["db_counts"].get(s, 0)
        marker = "" if n == db_n else f"  ← DB has {db_n}"
        print(f"    {s:15s} {n:4d}{marker}")
    if jsc["mismatches"]:
        print("  Mismatches:")
        for m in jsc["mismatches"]:
            print(f"    {m['status']}: YAML={m['yaml']} DB={m['db']}")

    # 2. Contract status counts
    csc = results["contract_status_counts"]
    print(f"\n[{indicator(csc['ok'])}] Contract Status Counts (YAML vs DB)")
    print(f"  YAML total: {csc['yaml_total']}  |  DB total: {csc['db_total']}")
    print("  Status breakdown (YAML):")
    for s, n in sorted(csc["yaml_counts"].items(), key=lambda x: -x[1]):
        db_n = csc["db_counts"].get(s, 0)
        marker = "" if n == db_n else f"  ← DB has {db_n}"
        print(f"    {s:15s} {n:4d}{marker}")

    # 3. Slug sync - jobs
    jss = results["job_slug_sync"]
    print(f"\n[{indicator(jss['ok'])}] Job Slug Sync (disk={jss['disk_count']} vs DB={jss['db_count']})")
    if jss["disk_only"]:
        print(f"  {len(jss['disk_only'])} slugs on disk but NOT in DB:")
        for s in jss["disk_only"][:10]:
            print(f"    - {s}")
        if len(jss["disk_only"]) > 10:
            print(f"    ... and {len(jss['disk_only']) - 10} more")
    if jss["db_only"]:
        print(f"  {len(jss['db_only'])} slugs in DB but NOT on disk:")
        for s in jss["db_only"][:10]:
            print(f"    - {s}")

    # 4. Slug sync - contracts
    css = results["contract_slug_sync"]
    print(f"\n[{indicator(css['ok'])}] Contract Slug Sync (disk={css['disk_count']} vs DB={css['db_count']})")
    if css["disk_only"]:
        print(f"  {len(css['disk_only'])} slugs on disk but NOT in DB:")
        for s in css["disk_only"][:10]:
            print(f"    - {s}")
        if len(css["disk_only"]) > 10:
            print(f"    ... and {len(css['disk_only']) - 10} more")
    if css["db_only"]:
        print(f"  {len(css['db_only'])} slugs in DB but NOT on disk:")
        for s in css["db_only"][:10]:
            print(f"    - {s}")

    # 5. File artifacts
    art = results["artifacts"]
    print(f"\n[{indicator(art['ok'])}] File Artifacts (built/submitted jobs: {art['checked']})")
    if art["missing"]:
        print(f"  {art['missing_count']} jobs missing PDFs:")
        for m in art["missing"][:10]:
            print(f"    {m['slug']} ({m['status']}): missing {', '.join(m['missing'])}")
        if len(art["missing"]) > 10:
            print(f"    ... and {len(art['missing']) - 10} more")
    else:
        print("  All built/submitted jobs have resume.pdf and cover_letter.pdf")

    # 6. Duplicate URLs
    dup = results["duplicate_urls"]
    print(f"\n[{warn_indicator(dup['duplicate_count'])}] Duplicate URLs ({dup['unique_urls']} unique)")
    if dup["duplicates"]:
        for url, slugs in list(dup["duplicates"].items())[:5]:
            print(f"  {url}")
            for s in slugs:
                print(f"    - {s}")

    # 7. Platform breakdown
    plat = results["platform_breakdown"]
    print(f"\n--- Platform Breakdown ---")
    for platform, info in sorted(plat.items(), key=lambda x: -x[1]["total"]):
        status_str = ", ".join(f"{s}={n}" for s, n in sorted(info["statuses"].items(), key=lambda x: -x[1]))
        print(f"  {platform:12s}  {info['total']:4d} jobs  submit_rate={info['submit_rate']:5.1f}%  ({status_str})")

    # 8. Block reasons
    blk = results["block_reasons"]
    print(f"\n--- Block Reason Analysis ({blk['total_blocked']} blocked) ---")
    for cat, count in sorted(blk["categories"].items(), key=lambda x: -x[1]):
        print(f"  {cat:35s}  {count:3d}")

    # 9. Timeline
    tl = results["timeline"]
    print(f"\n--- Scouting Timeline ---")
    for date, info in tl.items():
        status_str = ", ".join(f"{s}={n}" for s, n in sorted(info["statuses"].items(), key=lambda x: -x[1]))
        print(f"  {date:12s}  {info['total']:4d} jobs  ({status_str})")

    # 10. Company distribution
    comp = results["company_distribution"]
    print(f"\n--- Company Distribution ({comp['unique_companies']} unique) ---")
    print("  Top 10 by volume:")
    for company, info in comp["top_10_by_volume"]:
        status_str = ", ".join(f"{s}={n}" for s, n in sorted(info["statuses"].items(), key=lambda x: -x[1]))
        print(f"    {company:30s}  {info['total']:3d} jobs  submit={info['submit_rate']:5.1f}%  ({status_str})")

    # 11. Remote breakdown
    rem = results["remote_breakdown"]
    print(f"\n--- Remote/Onsite/Hybrid ---")
    for remote_type, info in sorted(rem.items(), key=lambda x: -x[1]["total"]):
        status_str = ", ".join(f"{s}={n}" for s, n in sorted(info["statuses"].items(), key=lambda x: -x[1]))
        print(f"  {remote_type:12s}  {info['total']:4d} jobs  ({status_str})")

    # Overall
    print("\n" + "=" * 70)
    all_checks = [jsc["ok"], csc["ok"], jss["ok"], css["ok"], art["ok"], dup["ok"]]
    passed = sum(all_checks)
    total = len(all_checks)
    print(f"  Validation: {passed}/{total} checks passed")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Explorer pipeline data")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    db_conn = open_db()
    yaml_jobs = load_all_jobs()
    yaml_contracts = load_all_contracts()

    results = {
        "generated_at": datetime.now().isoformat(),
        "job_status_counts": check_job_status_counts(yaml_jobs, db_conn),
        "contract_status_counts": check_contract_status_counts(yaml_contracts, db_conn),
        "job_slug_sync": check_slug_sync(set(yaml_jobs.keys()), db_conn, "jobs"),
        "contract_slug_sync": check_slug_sync(set(yaml_contracts.keys()), db_conn, "contracts"),
        "artifacts": check_artifacts(yaml_jobs),
        "duplicate_urls": check_duplicate_urls(yaml_jobs),
        "platform_breakdown": check_platform_breakdown(yaml_jobs),
        "block_reasons": check_block_reasons(yaml_jobs),
        "timeline": check_timeline(yaml_jobs),
        "company_distribution": check_company_distribution(yaml_jobs),
        "remote_breakdown": check_remote_breakdown(yaml_jobs),
    }

    db_conn.close()

    if args.json:
        # Convert Counter/tuple items for JSON serialization
        output = json.loads(json.dumps(results, default=str))
        # top_10_by_volume is a list of tuples, convert properly
        if "company_distribution" in output:
            output["company_distribution"]["top_10_by_volume"] = [
                {"company": c, **info} for c, info in results["company_distribution"]["top_10_by_volume"]
            ]
        print(json.dumps(output, indent=2))
    else:
        print_report(results)


if __name__ == "__main__":
    main()
