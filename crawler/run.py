"""CLI: python -m crawler.run [crawl|extract|stats|all] [--site NAME] [--limit N] [--days 30]"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

from . import db, extract, stats
from .adapters import saramin_web, ats, rallit, remember, saramin_api
from .adapters.common import RoleFilter
from .fetch import Fetcher, SiteAborted

ROOT = Path(__file__).resolve().parent.parent
ADAPTERS = {"remember": remember, "rallit": rallit, "saramin_api": saramin_api, "saramin_web": saramin_web, "ats": ats}


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def user_agent(g):
    """sites.yaml UA with the operator's contact from .env (COACH_CONTACT). Polite crawling needs a reachable contact."""
    load_env()
    contact = os.environ.get("COACH_CONTACT", "").strip()
    if not contact:
        raise SystemExit("Set COACH_CONTACT=<your email> in .env — sites can reach you instead of blocking (docs/OPERATIONS.md)")
    return g["user_agent"].replace("{contact}", contact)


def crawl(only=None, limit=None, days=None):
    cfg = yaml.safe_load((ROOT / "crawler" / "sites.yaml").read_text("utf-8"))
    companies = (yaml.safe_load((ROOT / "crawler" / "companies.yaml").read_text("utf-8")) or {}).get("companies", [])
    g = cfg["global"]
    days = days or g["recent_days"]
    rf = RoleFilter(g["role_include"], g["role_exclude"])
    con = db.connect()
    for name, site in cfg["sites"].items():
        if only and name != only:
            continue
        if not site.get("enabled") or name not in ADAPTERS:
            logging.info("skip %s (%s)", name, site.get("note", "disabled"))
            continue
        f = Fetcher(
            user_agent=user_agent(g),
            rate_per_sec=site.get("rate_per_sec", g["rate_per_sec"]),
            jitter=tuple(g["jitter_sec"]),
            max_requests=limit or site.get("max_requests", g["max_requests_per_site"]),
        )
        status, new = "ok", 0
        before = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        try:
            if name == "ats":
                new = ats.crawl(f, con, site, rf, days, companies)
            else:
                new = ADAPTERS[name].crawl(f, con, site, rf, days)
        except SiteAborted as e:
            status = f"aborted: {e}"
            logging.warning("%s aborted: %s", name, e)
        except Exception as e:  # one broken adapter must not stop the others
            status = f"error: {type(e).__name__}: {e}"
            logging.exception("%s failed", name)
        con.commit()
        new = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] - before
        con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?)", (db.now(), name, f.requests_made, f.cache_hits, new, status))
        con.commit()
        logging.info("%s: requests=%d cache_hits=%d new=%d status=%s", name, f.requests_made, f.cache_hits, new, status)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["crawl", "extract", "stats", "all"])
    p.add_argument("--site")
    p.add_argument("--limit", type=int, help="max requests per site (for testing)")
    p.add_argument("--days", type=int)
    p.add_argument("--force", action="store_true", help="re-extract all rows")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(ROOT / "data" / "crawl.log", encoding="utf-8")])
    load_env()
    if a.cmd in ("crawl", "all"):
        crawl(a.site, a.limit, a.days)
    if a.cmd in ("extract", "all"):
        logging.info("extracted %d rows", extract.run(a.force))
    if a.cmd in ("stats", "all"):
        o = stats.run(a.days or 30)
        logging.info("stats: %d postings, by_stage=%s", o["postings"], o["by_stage"])


if __name__ == "__main__":
    main()
