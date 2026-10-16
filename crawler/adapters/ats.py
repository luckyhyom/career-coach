"""Company career boards on public ATS APIs (Greenhouse, Lever).

Both expose an official, documented, unauthenticated JSON API for job boards:
  Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
  Lever:      https://api.lever.co/v0/postings/{slug}?mode=json
One request per company per run. Companies come from companies.yaml (ats + slug).
"""
from __future__ import annotations

import json
import logging

from .. import db
from .common import html_to_text, is_recent, parse_date

log = logging.getLogger("ats")


def _greenhouse(fetcher, slug):
    body = fetcher.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true", revalidate=True)
    for j in (json.loads(body).get("jobs", []) if body else []):
        yield {
            "source_id": f"gh:{slug}:{j['id']}", "url": j.get("absolute_url", ""), "title": j.get("title", ""),
            "posted": parse_date(j.get("first_published") or j.get("updated_at")),
            "location": (j.get("location") or {}).get("name", ""),
            "description": html_to_text(__import__("html").unescape(j.get("content") or "")),
        }


def _lever(fetcher, slug):
    body = fetcher.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", revalidate=True)
    for j in (json.loads(body) if body else []):
        lists = "\n".join(f"{l.get('text','')}\n{html_to_text(l.get('content'))}" for l in j.get("lists") or [])
        yield {
            "source_id": f"lv:{slug}:{j['id']}", "url": j.get("hostedUrl", ""), "title": j.get("text", ""),
            "posted": parse_date(j.get("createdAt")),
            "location": (j.get("categories") or {}).get("location", ""),
            "description": html_to_text(j.get("description")) + "\n" + lists,
        }


def _greeting_queries(page):
    from .common import next_data
    nd = next_data(page) if page else None
    return (((nd or {}).get("props") or {}).get("pageProps") or {}).get("dehydratedState", {}).get("queries", [])


def _greeting(fetcher, slug, role_filter=None, due=lambda sid: True):
    """Greeting(그리팅) career site: list in __NEXT_DATA__ 'openings'; detail page only for matching titles."""
    base = f"https://{slug}.career.greetinghr.com"
    qs = _greeting_queries(fetcher.get(base, revalidate=True))
    openings = next((q["state"]["data"] for q in qs if q.get("queryKey") == ["openings"]), []) or []
    for o in openings:
        title = o.get("title", "")
        if role_filter and not role_filter.match(title):
            continue
        oid = o.get("openingId")
        detail = ""
        dq = _greeting_queries(fetcher.get(f"{base}/o/{oid}", revalidate=due(f"gr:{slug}:{oid}")))
        for q in dq:
            if q.get("queryKey", [None, None])[:2] == ["career", "getOpeningById"]:
                detail = html_to_text(((q["state"]["data"].get("data") or {}).get("openingsInfo") or {}).get("detail"))
        pos = ((o.get("openingJobPosition") or {}).get("openingJobPositions") or [{}])[0]
        career = pos.get("jobPositionCareer") or {}
        yield {
            "source_id": f"gr:{slug}:{oid}", "url": f"{base}/o/{oid}", "title": title,
            "posted": parse_date(o.get("openDate")),
            "location": ((pos.get("workspacePlace") or {}).get("location")) or "",
            "description": detail,
            "experience": f"{career.get('careerType','')} {career.get('careerFrom') or ''}~{career.get('careerTo') or ''}년",
        }


def crawl(fetcher, con, cfg, role_filter, days, companies):
    new = 0
    for c in companies:
        ats, slug = c.get("ats"), c.get("slug")
        if ats not in ("greenhouse", "lever", "greeting") or not slug:
            continue
        try:
            if ats == "greeting":
                due = lambda sid: db.needs_recheck(con, "ats_greeting", sid, cfg.get("recheck_days", 14))
                postings = list(_greeting(fetcher, slug, role_filter, due))
            else:
                postings = list((_greenhouse if ats == "greenhouse" else _lever)(fetcher, slug))
        except (ValueError, KeyError) as e:
            log.warning("%s/%s: unexpected response (%s)", ats, slug, e)
            continue
        log.info("%s (%s/%s): %d postings", c["name"], ats, slug, len(postings))
        src = f"ats_{ats}"
        for p in postings:
            db.touch(con, src, p["source_id"])
            if not role_filter.match(p["title"]):
                continue
            # company boards are "open now"; keep regardless of age but record the date
            new += db.upsert_job(con, {
                "source": f"ats_{ats}", "source_id": p["source_id"], "url": p["url"],
                "company": c["name"], "title": p["title"],
                "posted_at": p["posted"].isoformat() if p["posted"] else None,
                "valid_through": None, "always_hiring": 0 if is_recent(p["posted"], days) else 1,
                "experience": p.get("experience", ""), "location": p["location"],
                "description": p["description"], "qualifications": "", "preferred": "",
                "source_skills": "[]", "salary": None, "steps": "[]",
            })
        # board listing is authoritative for this company: anything missing has closed
        n_closed = db.close_missing(con, src, [p["source_id"] for p in postings], company=c["name"])
        if n_closed:
            log.info("%s: closed %d", c["name"], n_closed)
        con.commit()
    return new
