"""리멤버 커리어: public sitemap -> posting pages with schema.org JobPosting JSON-LD.

The sitemap has ids only (no titles/dates), so we walk ids newest-first and stop after
`stop_after_old` consecutive postings older than the window. Non-matching ids are marked
as seen so they are never fetched again.
"""
from __future__ import annotations

import json
import logging
import re

from .. import db
from .common import html_to_text, is_recent, json_ld_blocks, parse_date, sitemap_locs

log = logging.getLogger("remember")
SOURCE = "remember"
SITEMAP = "https://career.rememberapp.co.kr/sitemap-jobs.xml"


def _org_name(org) -> str:
    if isinstance(org, dict):
        return org.get("name", "")
    return str(org or "")


def crawl(fetcher, con, cfg, role_filter, days):
    xml = fetcher.get(SITEMAP, revalidate=True)
    if not xml:
        return 0
    ids = sorted({int(m.group(1)) for u in sitemap_locs(xml) if (m := re.search(r"/job/posting/(\d+)", u))}, reverse=True)
    log.info("sitemap ids: %d", len(ids))
    new = old_streak = 0
    stop_after_old = cfg.get("stop_after_old", 150)
    for pid in ids:
        if db.was_seen(con, SOURCE, pid):
            continue
        url = f"https://career.rememberapp.co.kr/job/posting/{pid}"
        page = fetcher.get(url, revalidate=False)
        if not page:
            db.mark_seen(con, SOURCE, pid, False)
            continue
        jp = next((b for b in json_ld_blocks(page) if b.get("@type") == "JobPosting"), None)
        if not jp:
            db.mark_seen(con, SOURCE, pid, False)
            continue
        posted = parse_date(jp.get("datePosted"))
        if not is_recent(posted, days):
            old_streak += 1
            db.mark_seen(con, SOURCE, pid, False)
            if old_streak >= stop_after_old:
                log.info("stopping: %d consecutive postings older than %d days", old_streak, days)
                break
            continue
        old_streak = 0
        title = jp.get("title", "")
        desc = html_to_text(jp.get("description"))
        quals = html_to_text(jp.get("qualifications"))
        matched = role_filter.match(title, "")
        db.mark_seen(con, SOURCE, pid, matched)
        if not matched:
            continue
        loc = jp.get("jobLocation")
        if isinstance(loc, list) and loc:
            addr = (loc[0] or {}).get("address", {})
            loc = " ".join(filter(None, [addr.get("addressRegion"), addr.get("addressLocality")]))
        new += db.upsert_job(con, {
            "source": SOURCE, "source_id": str(pid), "url": url,
            "company": _org_name(jp.get("hiringOrganization")), "title": title,
            "posted_at": posted.isoformat() if posted else None,
            "valid_through": jp.get("validThrough") or None,
            "always_hiring": 0 if jp.get("validThrough") else 1,
            "experience": str(jp.get("experienceRequirements") or ""),
            "location": loc if isinstance(loc, str) else "",
            "description": desc, "qualifications": quals,
            "preferred": html_to_text(jp.get("preferredQualifications") or jp.get("skills")),
            "source_skills": json.dumps(jp.get("skills") if isinstance(jp.get("skills"), list) else [], ensure_ascii=False),
            "salary": json.dumps(jp.get("baseSalary"), ensure_ascii=False) if jp.get("baseSalary") else None,
            "steps": "[]",
        })
        con.commit()
    return new
