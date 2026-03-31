-- Explorer Job Registry Schema
-- Applied by import_to_db.py on first run; also usable as a DDL reference.

CREATE TABLE IF NOT EXISTS jobs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  slug          TEXT UNIQUE NOT NULL,
  url           TEXT UNIQUE NOT NULL,     -- PRIMARY dedup key
  apply_url     TEXT,
  company       TEXT NOT NULL,
  position      TEXT NOT NULL,
  location      TEXT,
  remote        TEXT,
  salary_range  TEXT,
  date_posted   TEXT,
  date_scouted  TEXT,
  source        TEXT,
  search_priority INTEGER,
  status        TEXT NOT NULL DEFAULT 'scouted',
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_url    ON jobs(url);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS contracts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  slug             TEXT UNIQUE NOT NULL,
  url              TEXT UNIQUE NOT NULL,   -- PRIMARY dedup key
  job_id           TEXT UNIQUE,            -- Upwork numeric job ID
  client           TEXT NOT NULL,
  title            TEXT NOT NULL,
  budget_type      TEXT,
  budget_low       REAL,
  budget_high      REAL,
  expertise_level  TEXT,
  status           TEXT NOT NULL DEFAULT 'scouted',
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_contracts_url    ON contracts(url);
CREATE INDEX IF NOT EXISTS idx_contracts_job_id ON contracts(job_id);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
