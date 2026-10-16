"""사람인 오픈 API (official). Needs an access key: https://oapi.saramin.co.kr/
Set SARAMIN_ACCESS_KEY in .env. Covers Saramin postings (and therefore many 중견/대기업 공고).
"""
from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlencode

from .. import db
from .common import is_recent, parse_date

log = logging.getLogger("saramin")
API = "https://oapi.saramin.co.kr/job-search"


def crawl(fetcher, con, cfg, role_filter, days):
    key = os.environ.get("SARAMIN_ACCESS_KEY")
    if not key:
        log.info("SARAMIN_ACCESS_KEY not set; skipping")
        return 0
    new, start = 0, 0
    while True:
        q = {"access-key": key, "keywords": cfg.get("keywords", "백엔드"), "job_mid_cd": 2,
             "count": 110, "start": start, "sort": "pd"}
        body = fetcher.get(f"{API}?{urlencode(q)}", use_cache=False)
        if not body:
            break
        data = json.loads(body).get("jobs", {})
        items = data.get("job", [])
        if not items:
            break
        stop = False
        for j in items:
            posted = parse_date(j.get("posting-timestamp"))
            if not is_recent(posted, days):
                stop = True
                break
            pos = j.get("position", {})
            title = pos.get("title", "")
            if not role_filter.match(title, (pos.get("job-code") or {}).get("name", "")):
                continue
            new += db.upsert_job(con, {
                "source": "saramin", "source_id": str(j.get("id")), "url": j.get("url", ""),
                "company": ((j.get("company") or {}).get("detail") or {}).get("name", ""), "title": title,
                "posted_at": posted.isoformat() if posted else None,
                "valid_through": parse_date(j.get("expiration-timestamp")).isoformat() if j.get("expiration-timestamp") else None,
                "always_hiring": 0, "experience": (pos.get("experience-level") or {}).get("name", ""),
                "location": (pos.get("location") or {}).get("name", ""),
                "description": "", "qualifications": "", "preferred": "",
                "source_skills": json.dumps((j.get("keyword") or "").split(","), ensure_ascii=False),
                "salary": (j.get("salary") or {}).get("name"), "steps": "[]",
            })
        con.commit()
        if stop or len(items) < 110:
            break
        start += 1
    return new
