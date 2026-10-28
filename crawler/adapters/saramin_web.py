"""사람인 웹 공고 (API 키 승인 전 임시). robots.txt가 허용하는 검색 목록과 상세 본문(iframe)만 읽는다.

- 2026-10-28 robots.txt 확인: User-agent *에 /zf_user/search, /zf_user/jobs/relay/* 는 막혀 있지 않다.
- 차단(403·챌린지)이 오면 SiteAborted로 즉시 중단한다. 우회하지 않는다.
- **개인 분석용**: 이 데이터로 만든 통계·페르소나를 서비스에 그대로 쓰지 않는다(docs/DATA.md).
- SARAMIN_ACCESS_KEY가 있으면 공식 API(saramin_api)를 쓰고 이 어댑터는 건너뛴다.
"""
from __future__ import annotations

import html
import logging
import os
import re
from datetime import date, datetime
from urllib.parse import quote

from .. import db
from .common import html_to_text, is_recent

log = logging.getLogger("saramin_web")
SOURCE = "saramin_web"
BASE = "https://www.saramin.co.kr"
LIST = BASE + "/zf_user/search/recruit?searchType=search&searchword={kw}&recruitPage={page}&recruitPageCount=40&recruitSort=reg_dt"
DETAIL = BASE + "/zf_user/jobs/relay/view-detail?rec_idx={rid}&rec_seq=0"
VIEW = BASE + "/zf_user/jobs/relay/view?rec_idx={rid}"
BACKEND_SECTORS = ("백엔드/서버개발",)
MIN_TEXT = 200  # image-only postings carry almost no text; nothing to analyze


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_list(page: str) -> list[dict]:
    items = []
    chunks = re.split(r'<div class="item_recruit"', page)[1:]
    for c in chunks:
        rid = re.search(r'value="(\d+)"', c)
        title = re.search(r'<h2 class="job_tit">.*?title="([^"]*)"', c, re.S)
        corp = re.search(r'<strong class="corp_name">\s*<a[^>]*>(.*?)</a>', c, re.S)
        cond = re.search(r'<div class="job_condition">(.*?)</div>', c, re.S)
        sector = re.search(r'<div class="job_sector">(.*?)</div>', c, re.S)
        reg = re.search(r"등록일\s*(\d{2})/(\d{2})/(\d{2})", c)
        due = re.search(r'<span class="date">\s*([^<]*)</span>', c)
        if not (rid and title):
            continue
        spans = [_clean(s) for s in re.findall(r"<span>(.*?)</span>", cond.group(1), re.S)] if cond else []
        items.append({
            "rid": rid.group(1), "title": html.unescape(title.group(1)), "company": _clean(corp.group(1)) if corp else "",
            "location": spans[0] if spans else "", "experience": spans[1] if len(spans) > 1 else "",
            "sectors": [_clean(b) for b in re.findall(r"<b>(.*?)</b>", sector.group(1), re.S)] if sector else [],
            "posted": date(2000 + int(reg.group(1)), int(reg.group(2)), int(reg.group(3))) if reg else None,
            "due": _clean(due.group(1)) if due else "",
        })
    return items


def _due_date(due: str, posted: date | None):
    m = re.search(r"(\d{2})/(\d{2})", due or "")
    if not m:
        return None  # 상시채용·채용시 마감
    today = date.today()
    y = today.year + (1 if int(m.group(1)) < today.month - 6 else 0)
    try:
        return date(y, int(m.group(1)), int(m.group(2))).isoformat()
    except ValueError:
        return None


def crawl(fetcher, con, cfg, role_filter, days):
    if os.environ.get("SARAMIN_ACCESS_KEY"):
        log.info("SARAMIN_ACCESS_KEY set -> official API is used instead; skipping web")
        return 0
    new, seen_now = 0, set()
    for kw in cfg.get("keywords", ["백엔드"]):
        for page_no in range(1, cfg.get("max_pages", 5) + 1):
            page = fetcher.get(LIST.format(kw=quote(kw), page=page_no), use_cache=False)
            items = parse_list(page or "")
            if not items:
                break
            old = 0
            for it in items:
                if it["posted"] and not is_recent(it["posted"], days):
                    old += 1
                    continue
                matched = role_filter.match(it["title"], " ".join(it["sectors"])) or (
                    any(s in BACKEND_SECTORS for s in it["sectors"]) and not role_filter.excluded(it["title"]))
                if not matched or it["rid"] in seen_now:
                    continue
                seen_now.add(it["rid"])
                if db.was_seen(con, SOURCE, it["rid"]):
                    db.touch(con, SOURCE, it["rid"])  # still listed -> stays in the "open" view
                    continue
                body = fetcher.get(DETAIL.format(rid=it["rid"]), revalidate=False)
                text = html_to_text(re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body or "", flags=re.S))
                ok = len(text) >= MIN_TEXT
                db.mark_seen(con, SOURCE, it["rid"], ok)
                if not ok:
                    continue
                new += db.upsert_job(con, {
                    "source": SOURCE, "source_id": it["rid"], "url": VIEW.format(rid=it["rid"]),
                    "company": it["company"], "title": it["title"],
                    "posted_at": it["posted"].isoformat() if it["posted"] else None,
                    "valid_through": _due_date(it["due"], it["posted"]), "always_hiring": int("상시" in it["due"]),
                    "experience": it["experience"], "location": it["location"],
                    "description": text, "qualifications": "", "preferred": "",
                    "source_skills": "[]", "salary": "", "steps": "[]",
                })
                con.commit()
            if old == len(items):  # sorted by registration date: the rest is older than the window
                break
    # deadline passed -> closed (search listings are not exhaustive, so absence alone never closes)
    n = con.execute("UPDATE jobs SET status='closed', closed_at=? WHERE source=? AND COALESCE(status,'open')='open' "
                    "AND valid_through IS NOT NULL AND valid_through < ?",
                    (db.now(), SOURCE, date.today().isoformat())).rowcount
    con.commit()
    log.info("saramin_web: listed backend=%d new=%d closed_by_deadline=%d", len(seen_now), new, n)
    return new
