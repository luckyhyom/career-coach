"""Single definition of "which postings count" — shared by stats, insight and persona_build.

Tiers (by posting date, independent of whether it's still open):
  recent        posted within `recent_days`
  open_older    posted earlier, still open (always-hiring / long-running)
  unknown_date  site gives no posting date

Views:
  open    status='open' and seen within `open_within_days` of the latest crawl  -> "현재 모집 중 시장" (personas)
  recent  open AND tier=recent                                                 -> "최근 N일 신규 채용 동향"

Common filters (from sites.yaml global.population): Korea-only, frontend titles excluded, min_years cap.
Every output records the population spec it used (`describe()`), so stats and personas are comparable.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from .adapters.common import RoleFilter

ROOT = Path(__file__).resolve().parent.parent
ABROAD = re.compile(r"usa|united states|india|bengaluru|hyderabad|singapore|china|shanghai|taiwan|taipei|japan|tokyo|"
                    r"seattle|mountain view|new york|nyc|london|remote - us|vietnam|hanoi", re.I)


def config() -> dict:
    g = yaml.safe_load((ROOT / "crawler" / "sites.yaml").read_text("utf-8"))["global"]
    p = g.get("population", {})
    return {"recent_days": p.get("recent_days", g.get("recent_days", 30)),
            "open_within_days": p.get("open_within_days", 14),
            "max_min_years": p.get("max_min_years", 7),
            "korea_only": p.get("korea_only", True),
            "persona_view": p.get("persona_view", "open")}


def tier(row, recent_days: int) -> str:
    if not row["posted_at"]:
        return "unknown_date"
    return "recent" if row["posted_at"] >= (date.today() - timedelta(days=recent_days)).isoformat() else "open_older"


def select(con, view: str = "open", require_insight: bool = False, cfg: dict = None):
    """Return rows (sqlite Row) with an extra 'tier' key, filtered by the common spec."""
    cfg = cfg or config()
    latest = con.execute("SELECT MAX(last_seen) FROM jobs").fetchone()[0] or datetime.now().isoformat()
    since = (datetime.fromisoformat(latest[:19]) - timedelta(days=cfg["open_within_days"])).isoformat()
    q = "SELECT j.* FROM jobs j" + (" JOIN job_insights i ON i.uid=j.uid" if require_insight else "") + \
        " WHERE COALESCE(j.status,'open')='open' AND j.last_seen >= ?"
    rf = RoleFilter([], [])
    out = []
    for r in con.execute(q, (since,)).fetchall():
        if cfg["korea_only"] and ABROAD.search(r["location"] or ""):
            continue
        if rf.excluded(r["title"]):
            continue
        if cfg["max_min_years"] is not None and r["min_years"] is not None and r["min_years"] > cfg["max_min_years"]:
            continue
        t = tier(r, cfg["recent_days"])
        if view == "recent" and t != "recent":
            continue
        d = dict(r)
        d["tier"] = t
        out.append(d)
    return out


def describe(rows, view: str, cfg: dict = None) -> dict:
    cfg = cfg or config()
    tiers = {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    return {"view": view, "postings": len(rows), "tiers": tiers,
            "spec": {k: cfg[k] for k in ("recent_days", "open_within_days", "max_min_years", "korea_only")},
            "note": {"open": "현재 모집 중 공고(게시일 무관). 최근 신규 채용 동향이 아님",
                     "recent": f"최근 {cfg['recent_days']}일 내 게시 + 현재 모집 중"}[view]}


def resolve_stage(company: str, insight: dict = None, stage_map: dict = None):
    """Shared stage resolution: companies.yaml > quote-verified posting hint > unknown. Returns (stage, source)."""
    from .db import _norm
    from .stats import company_stage_map
    stage_map = stage_map if stage_map is not None else company_stage_map()
    st = stage_map.get(_norm(company))
    if st and st != "unknown":
        return st, "companies.yaml"
    hint = ((insight or {}).get("stage_hint") or {}).get("value", "unknown")
    return (hint, "posting_hint") if hint != "unknown" else ("unknown", None)
