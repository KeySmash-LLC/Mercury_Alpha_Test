#!/usr/bin/env python3
"""
One-time (and idempotent) import script: seeds explorer.db from existing
data/jobs/*/job.yaml and data/contracts/*/contract.yaml files.

Safe to run multiple times — uses INSERT OR IGNORE so duplicates are silently
skipped. Run from the Explorer/ directory:

    python scripts/import_to_db.py
"""

import glob
import pathlib
import re
import sqlite3
import sys

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = pathlib.Path(__file__).parent
EXPLORER_DIR = SCRIPT_DIR.parent
DB_PATH = EXPLORER_DIR / "data" / "explorer.db"
SCHEMA_PATH = EXPLORER_DIR / "data" / "schema.sql"

MALFORMED_SLUG_RE = re.compile(r"[ &;|]")  # spaces or shell-injection chars


def open_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    schema_sql = SCHEMA_PATH.read_text()
    conn.executescript(schema_sql)
    conn.commit()
    return conn


def import_jobs(conn: sqlite3.Connection) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    pattern = str(EXPLORER_DIR / "data" / "jobs" / "*" / "job.yaml")
    for yaml_path in sorted(glob.glob(pattern)):
        p = pathlib.Path(yaml_path)
        slug = p.parent.name

        # Skip ghost/malformed directories
        if MALFORMED_SLUG_RE.search(slug):
            skipped += 1
            continue

        try:
            data = yaml.safe_load(p.read_text())
        except Exception as e:
            print(f"  WARN: could not parse {yaml_path}: {e}", file=sys.stderr)
            skipped += 1
            continue

        url = data.get("url") or ""
        if not url:
            skipped += 1
            continue

        company = data.get("company") or ""
        position = data.get("position") or ""
        if not company or not position:
            skipped += 1
            continue

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO jobs
              (slug, url, apply_url, company, position, location, remote,
               salary_range, date_posted, date_scouted, source, search_priority, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                url,
                data.get("apply_url"),
                company,
                position,
                data.get("location"),
                data.get("remote"),
                data.get("salary_range"),
                data.get("date_posted"),
                data.get("date_scouted"),
                data.get("source"),
                data.get("search_priority"),
                data.get("status") or "scouted",
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    return inserted, skipped


def import_contracts(conn: sqlite3.Connection) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    pattern = str(EXPLORER_DIR / "data" / "contracts" / "*" / "contract.yaml")
    for yaml_path in sorted(glob.glob(pattern)):
        p = pathlib.Path(yaml_path)
        slug = p.parent.name

        if MALFORMED_SLUG_RE.search(slug):
            skipped += 1
            continue

        try:
            data = yaml.safe_load(p.read_text())
        except Exception as e:
            print(f"  WARN: could not parse {yaml_path}: {e}", file=sys.stderr)
            skipped += 1
            continue

        url = data.get("url") or ""
        if not url:
            skipped += 1
            continue

        client = data.get("client") or ""
        title = data.get("title") or ""
        if not client or not title:
            skipped += 1
            continue

        job_id = data.get("job_id") or None

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO contracts
              (slug, url, job_id, client, title, budget_type,
               budget_low, budget_high, expertise_level, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                url,
                job_id,
                client,
                title,
                data.get("budget_type"),
                data.get("budget_low"),
                data.get("budget_high"),
                data.get("expertise_level"),
                data.get("status") or "scouted",
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    return inserted, skipped


def main() -> None:
    conn = open_db()

    print(f"DB: {DB_PATH}")
    print("Importing jobs...")
    jobs_in, jobs_skip = import_jobs(conn)
    print(f"  Imported {jobs_in} jobs ({jobs_skip} skipped as duplicates/invalid)")

    print("Importing contracts...")
    cont_in, cont_skip = import_contracts(conn)
    print(f"  Imported {cont_in} contracts ({cont_skip} skipped as duplicates/invalid)")

    # Spot-check counts
    (job_total,) = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
    (cont_total,) = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()
    print(f"\nDB totals: {job_total} jobs, {cont_total} contracts")

    # Status breakdown
    print("\nJobs by status:")
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status ORDER BY n DESC"):
        print(f"  {row['status']}: {row['n']}")

    print("\nContracts by status:")
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM contracts GROUP BY status ORDER BY n DESC"):
        print(f"  {row['status']}: {row['n']}")

    conn.close()


if __name__ == "__main__":
    main()
