from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid            TEXT PRIMARY KEY,     -- hash of normalized (company, title)
    source         TEXT NOT NULL,
    source_id      TEXT NOT NULL,
    url            TEXT NOT NULL,
    company        TEXT,
    title          TEXT,
    posted_at      TEXT,                 -- ISO date if known
    valid_through  TEXT,
    always_hiring  INTEGER DEFAULT 0,
    experience     TEXT,                 -- raw text from source
    location       TEXT,
    description    TEXT,                 -- plain text
    qualifications TEXT,
    preferred      TEXT,
    source_skills  TEXT,                 -- JSON list provided by the site, if any
    salary         TEXT,
    steps          TEXT,                 -- JSON list of hiring steps, if any
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    also_on        TEXT DEFAULT '[]',    -- JSON list of other source URLs (cross-site duplicates)
    -- extracted by extract.py
    is_backend     INTEGER,
    skills         TEXT,                 -- JSON list (normalized)
    min_years      INTEGER,
    max_years      INTEGER,
    coding_test    INTEGER,
    assignment     INTEGER,
    extracted_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_source ON jobs(source, source_id);
CREATE TABLE IF NOT EXISTS seen (            -- source ids already checked (incl. non-matching), to avoid refetch
    source TEXT, source_id TEXT, checked_at TEXT, matched INTEGER,
    PRIMARY KEY (source, source_id)
);
CREATE TABLE IF NOT EXISTS runs (
    started_at TEXT, site TEXT, requests INTEGER, cache_hits INTEGER, new_jobs INTEGER, status TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=120)
    con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
    if "content_hash" not in cols:  # migration: change detection
        con.execute("ALTER TABLE jobs ADD COLUMN content_hash TEXT")
    return con


def content_hash(job: dict) -> str:
    body = "\n".join(str(job.get(k) or "") for k in ("title", "description", "qualifications", "preferred", "experience"))
    return hashlib.sha1(re.sub(r"\s+", " ", body).strip().encode()).hexdigest()[:16]


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(주\)|㈜|주식회사|inc\.?|corp\.?|co\.,? ?ltd\.?", "", s)
    s = re.sub(r"[\s\(\)\[\]\-_/·,.|]+", "", s)
    return s


def make_uid(company: str, title: str) -> str:
    return hashlib.sha1(f"{_norm(company)}|{_norm(title)}".encode()).hexdigest()[:16]


def upsert_job(con: sqlite3.Connection, job: dict) -> bool:
    """Insert or update. Returns True if this is a new posting."""
    ts = now()
    uid = make_uid(job.get("company", ""), job.get("title", ""))
    row = con.execute("SELECT uid, source, url, also_on FROM jobs WHERE uid=?", (uid,)).fetchone()
    if row and row["source"] != job["source"]:
        # same posting on another site -> just remember the other URL
        also = set(json.loads(row["also_on"] or "[]"))
        also.add(job["url"])
        con.execute("UPDATE jobs SET also_on=?, last_seen=? WHERE uid=?", (json.dumps(sorted(also)), ts, uid))
        return False
    job = dict(job, content_hash=content_hash(job))
    cols = ["source", "source_id", "url", "company", "title", "posted_at", "valid_through", "always_hiring",
            "experience", "location", "description", "qualifications", "preferred", "source_skills", "salary", "steps",
            "content_hash"]
    vals = [job.get(c) for c in cols]
    if row:
        old = con.execute("SELECT content_hash FROM jobs WHERE uid=?", (uid,)).fetchone()[0]
        if old == job["content_hash"]:
            con.execute("UPDATE jobs SET last_seen=? WHERE uid=?", (ts, uid))  # unchanged: no re-extract / re-analysis
            return False
        sets = ", ".join(f"{c}=?" for c in cols) + ", last_seen=?, extracted_at=NULL"
        con.execute(f"UPDATE jobs SET {sets} WHERE uid=?", vals + [ts, uid])
        # body changed -> drop cached LLM insight so it is re-analyzed once
        try:
            con.execute("DELETE FROM job_insights WHERE uid=?", (uid,))
        except Exception:
            pass
        return False
    con.execute(
        f"INSERT OR IGNORE INTO jobs (uid, {', '.join(cols)}, first_seen, last_seen) VALUES (?{', ?' * len(cols)}, ?, ?)",
        [uid] + vals + [ts, ts],
    )
    return True


def mark_seen(con: sqlite3.Connection, source: str, source_id: str, matched: bool) -> None:
    con.execute("INSERT OR REPLACE INTO seen VALUES (?, ?, ?, ?)", (source, str(source_id), now(), int(matched)))


def was_seen(con: sqlite3.Connection, source: str, source_id: str) -> bool:
    return con.execute("SELECT 1 FROM seen WHERE source=? AND source_id=?", (source, str(source_id))).fetchone() is not None
