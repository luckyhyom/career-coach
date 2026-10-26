"""회사 채용 보드 slug 탐색기: 후보 slug가 Greenhouse / Greeting에 있는지 1건씩 확인한다.

    .venv/bin/python -m crawler.probe_boards toss daangn musinsa ...

slug당 최대 2요청, 같은 rate limit 적용. 찾은 것은 companies.yaml에 ats/slug로 추가하면 된다.
"""
from __future__ import annotations

import json
import sys

import yaml

from .adapters.ats import _greeting_queries
from .fetch import Fetcher, SiteAborted
from .run import ROOT, user_agent


def main(slugs):
    g = yaml.safe_load((ROOT / "crawler" / "sites.yaml").read_text("utf-8"))["global"]
    f = Fetcher(user_agent(g), rate_per_sec=0.5, max_requests=len(slugs) * 2 + 10)
    for s in slugs:
        found = []
        try:
            body = f.get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs", use_cache=False)
            if body:
                found.append(f"greenhouse ({len(json.loads(body).get('jobs', []))}건)")
            qs = _greeting_queries(f.get(f"https://{s}.career.greetinghr.com", use_cache=False))
            ops = next((q["state"]["data"] for q in qs if q.get("queryKey") == ["openings"]), None)
            if ops is not None:
                found.append(f"greeting ({len(ops)}건)")
        except SiteAborted as e:
            found.append(f"중단: {e}")
        print(f"{s:20s} {', '.join(found) or '-'}")


if __name__ == "__main__":
    main(sys.argv[1:])
