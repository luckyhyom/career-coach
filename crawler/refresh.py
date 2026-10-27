"""Keep posting data current: if the last successful crawl is older than today, re-run the pipeline.

    crawl → extract → stats (LLM 0) → insight (new/changed postings only) → persona_build → persona_write (only changed bands)

Called by `coach.cli` before review/panel/target. Skip with `--no-refresh` or COACH_AUTO_REFRESH=off.
"""
from __future__ import annotations

import fcntl
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime

from .run import ROOT

DB = ROOT / "data" / "jobs.sqlite"
LOCK = ROOT / "data" / "refresh.lock"
STEPS = [
    ("수집·추출·통계", ["-m", "crawler.run", "all"]),
    ("공고 해석 (신규·변경분만)", ["-m", "crawler.insight", "run", "--workers", "4"]),
    ("페르소나 수치", ["-m", "crawler.persona_build"]),
    ("페르소나 카드 (입력이 바뀐 단계만)", ["-m", "crawler.persona_write"]),
]


def last_crawl() -> date | None:
    """Local date of the latest crawl run with at least one site finishing ok."""
    if not DB.exists():
        return None
    try:
        con = sqlite3.connect(DB)
        row = con.execute("SELECT MAX(started_at) FROM runs WHERE status='ok'").fetchone()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    return datetime.fromisoformat(row[0]).astimezone().date()


def is_stale(today: date | None = None) -> bool:
    last = last_crawl()
    return last is None or last < (today or date.today())


def refresh(log=print) -> bool:
    """Run the pipeline once (cross-process lock). Returns True if every step succeeded."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("다른 프로세스가 이미 공고를 갱신 중입니다. 끝날 때까지 기다립니다...")
            fcntl.flock(lk, fcntl.LOCK_EX)
            return not is_stale()
        if not is_stale():  # someone else finished while we waited for the lock
            return True
        for label, args in STEPS:
            log(f"  · {label}")
            r = subprocess.run([sys.executable, *args], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if r.returncode != 0:
                log(f"    실패 (exit {r.returncode}): {(r.stderr or '').strip().splitlines()[-1:] or ''} — 기존 데이터로 계속합니다")
                return False
        return True


def ensure_fresh(enabled: bool = True, log=print) -> date | None:
    """Refresh if stale. Never raises: a failed refresh falls back to the data already on disk."""
    if not enabled or os.environ.get("COACH_AUTO_REFRESH", "on").lower() in ("off", "0", "false", "no"):
        return last_crawl()
    last = last_crawl()
    if last is not None and last >= date.today():
        return last
    log(f"공고 데이터가 {'없습니다' if last is None else f'{last} 기준입니다'}. 오늘 기준으로 새로 모읍니다"
        f" (증분 수집, 보통 수 분{'. 처음이면 수 시간' if last is None else ''}; 건너뛰려면 --no-refresh)")
    refresh(log)
    return last_crawl()
