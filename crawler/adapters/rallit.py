"""랠릿: public server-sitemap lists every open position -> page __NEXT_DATA__.

Rallit has many always-hiring positions without a real posting date, so a position that is
currently in the sitemap counts as "open now" (posted_at = approvedAt).
"""
from __future__ import annotations

import json
import logging
import re

from .. import db
from .common import html_to_text, is_recent, next_data, parse_date, sitemap_locs

log = logging.getLogger("rallit")
SOURCE = "rallit"
SITEMAP = "https://www.rallit.com/server-sitemap.xml"
BACKEND_CODES = {"BACKEND_DEVELOPER", "FULLSTACK_DEVELOPER"}  # SOFTWARE_ENGINEER etc. only if the title matches


def crawl(fetcher, con, cfg, role_filter, days):
    xml = fetcher.get(SITEMAP, revalidate=True)
    if not xml:
        return 0
    urls = [u for u in sitemap_locs(xml) if "/positions/" in u]
    log.info("open positions in sitemap: %d", len(urls))
    new = 0
    for url in urls:
        m = re.search(r"/positions/(\d+)", url)
        if not m:
            continue
        pid = m.group(1)
        if db.was_seen(con, SOURCE, pid):
            con.execute("UPDATE jobs SET last_seen=? WHERE source=? AND source_id=?", (db.now(), SOURCE, pid))
            continue
        page = fetcher.get(url, revalidate=False)  # sitemap URL includes the slug (bare id -> 308)
        nd = next_data(page) if page else None
        p = (((nd or {}).get("props") or {}).get("pageProps") or {}).get("position")
        if not p:
            db.mark_seen(con, SOURCE, pid, False)
            continue
        codes = {j.get("code") for j in p.get("jobs") or []}
        title = p.get("title", "")
        matched = role_filter.match(title) or (bool(codes & BACKEND_CODES) and not role_filter.excluded(title))
        approved = parse_date(p.get("approvedAt"))
        always = bool(p.get("isAlwaysHiring")) or (p.get("endedAt") or "").startswith("9999")
        recent = always or is_recent(approved, days) or (p.get("status") or {}).get("code") == "HIRING"
        db.mark_seen(con, SOURCE, pid, matched and recent)
        if not (matched and recent):
            continue
        new += db.upsert_job(con, {
            "source": SOURCE, "source_id": pid, "url": f"https://www.rallit.com/positions/{pid}",
            "company": p.get("companyName", ""), "title": p.get("title", ""),
            "posted_at": approved.isoformat() if approved else None,
            "valid_through": None if always else p.get("endedAt"),
            "always_hiring": int(always),
            "experience": ",".join(p.get("jobLevels") or []),
            "location": (p.get("addressRegion") or {}).get("name", ""),
            "description": html_to_text((p.get("description") or "") + "\n" + (p.get("responsibilities") or "")),
            "qualifications": html_to_text(p.get("basicQualifications")),
            "preferred": html_to_text(p.get("preferredQualifications")),
            "source_skills": json.dumps(p.get("jobSkillKeywords") or [], ensure_ascii=False),
            "salary": str(p.get("minimumSalary") or ""),
            "steps": json.dumps(p.get("positionSteps") or [], ensure_ascii=False),
        })
        con.commit()
    return new
