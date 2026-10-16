from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional


def html_to_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "• ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def json_ld_blocks(page: str) -> List[dict]:
    out = []
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            d = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        out.extend(d if isinstance(d, list) else [d])
    return out


def next_data(page: str) -> Optional[dict]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    return json.loads(m.group(1)) if m else None


def sitemap_locs(xml: str) -> List[str]:
    return [html.unescape(u) for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)]


def parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip()
    if re.fullmatch(r"\d{10,13}", s):  # epoch seconds / ms
        n = int(s)
        return datetime.utcfromtimestamp(n / 1000 if n > 1e11 else n).date()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[: len(datetime.now().strftime(fmt))], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def is_recent(d: Optional[date], days: int) -> bool:
    return d is not None and d >= date.today() - timedelta(days=days)


class RoleFilter:
    def __init__(self, include: Iterable[str], exclude: Iterable[str]):
        self.include = [k.lower() for k in include]
        self.exclude = [k.lower() for k in exclude]

    def excluded(self, title: str) -> bool:
        t = (title or "").lower()
        return any(x in t for x in self.exclude)

    def match(self, title: str, extra: str = "") -> bool:
        t = (title or "").lower()
        if self.excluded(t):
            return False
        hay = t + " " + (extra or "").lower()
        return any(k in hay for k in self.include)
