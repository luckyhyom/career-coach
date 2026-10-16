"""Aggregate stats per company stage -> data/stats/*.json (+ summary.md). No LLM."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import db
from .db import _norm
from .extract import load_skill_patterns
from .adapters.common import RoleFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "stats"
STAGES = ["seed", "series_a", "series_b", "series_c_plus", "pre_ipo_unicorn", "listed_mid",
          "enterprise", "big_tech", "foreign", "si_agency", "unknown"]


def company_stage_map() -> dict:
    data = yaml.safe_load((ROOT / "crawler" / "companies.yaml").read_text("utf-8")) or {}
    m = {}
    for c in data.get("companies", []):
        for name in [c["name"]] + c.get("aliases", []):
            m[_norm(name)] = c.get("stage", "unknown")
    return m


REQ_LINE = re.compile(r"^\s*(?:[•\-\*·▪︎◦]|\d+[.)])?\s*(.{12,160})$")


def _requirement_lines(rows, top_skill_names, per_field=12):
    """Representative real requirement sentences (verbatim) with their posting uid.

    Lines that mention one of the stage's top skills are preferred, deduplicated, spread across companies.
    """
    out = {"qualifications": [], "preferred": []}
    for field in out:
        seen_text, per_company = set(), Counter()
        cands = []
        for r in rows:
            text = r[field] or ""
            if field == "qualifications" and not text:
                text = r["description"] or ""  # boards without a separate field
            for line in text.splitlines():
                m = REQ_LINE.match(line)
                if not m:
                    continue
                s = m.group(1).strip()
                key = re.sub(r"\W+", "", s.lower())[:60]
                if key in seen_text:
                    continue
                hits = sum(1 for k in top_skill_names if k.lower() in s.lower())
                cands.append((hits, r["company"], r["uid"], s))
                seen_text.add(key)
        for hits, company, uid, s in sorted(cands, key=lambda c: -c[0]):
            if per_company[company] >= 2:
                continue
            out[field].append({"text": s, "uid": uid, "company": company})
            per_company[company] += 1
            if len(out[field]) >= per_field:
                break
    return out


def _summ(rows, groups):
    n = len(rows)
    skills = Counter()
    for r in rows:
        skills.update(json.loads(r["skills"] or "[]"))
    years = [r["min_years"] for r in rows if r["min_years"] is not None]
    by_group = defaultdict(list)
    for s, c in skills.most_common():
        by_group[groups.get(s, "other")].append({"skill": s, "count": c, "pct": round(100 * c / n, 1) if n else 0})
    return {
        "postings": n,
        "coding_test_pct": round(100 * sum(r["coding_test"] or 0 for r in rows) / n, 1) if n else 0,
        "assignment_pct": round(100 * sum(r["assignment"] or 0 for r in rows) / n, 1) if n else 0,
        "min_years_dist": dict(sorted(Counter(min(y, 10) for y in years).items())),
        "top_skills": [{"skill": s, "count": c, "pct": round(100 * c / n, 1)} for s, c in skills.most_common(40)] if n else [],
        "skills_by_group": by_group,
        "sample_uids": [r["uid"] for r in rows[:15]],
        # verbatim requirement sentences so personas judge against real wording, not just counts
        "sample_requirements": _requirement_lines(rows, [s for s, _ in skills.most_common(15)]) if n else {},
    }


def run(days: int = 30, max_years: int = 7) -> dict:
    """Stats on the shared population (crawler/population.py). `open` = 현재 모집 중, `recent` = 최근 게시."""
    from . import population as P
    con = db.connect()
    stage_of = company_stage_map()
    groups = {name: g for name, (g, _) in load_skill_patterns().items()}
    cfg = P.config()
    rows = [r for r in P.select(con, "open", cfg=cfg) if r.get("extracted_at")]
    recent_rows = [r for r in rows if r["tier"] == "recent"]
    by_stage = defaultdict(list)
    unknown = Counter()
    ins_of = {u: json.loads(d) for u, d in con.execute("SELECT uid, data FROM job_insights")} if \
        con.execute("SELECT name FROM sqlite_master WHERE name='job_insights'").fetchone() else {}
    for r in rows:
        st, _ = P.resolve_stage(r["company"], ins_of.get(r["uid"]), stage_of)
        by_stage[st].append(r)
        if st == "unknown":
            unknown[r["company"]] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    overall = _summ(rows, groups)
    overall["population"] = P.describe(rows, "open", cfg)
    overall["by_source"] = dict(Counter(r["source"] for r in rows))
    overall["by_stage"] = {s: len(by_stage.get(s, [])) for s in STAGES}
    overall["unclassified_companies"] = unknown.most_common(50)
    overall["window_days"] = cfg["recent_days"]
    overall["generated"] = date.today().isoformat()
    (OUT / "overall.json").write_text(json.dumps(overall, ensure_ascii=False, indent=1), "utf-8")
    recent = _summ(recent_rows, groups)
    recent["population"] = P.describe(recent_rows, "recent", cfg)
    (OUT / "recent.json").write_text(json.dumps(recent, ensure_ascii=False, indent=1), "utf-8")
    for st in STAGES:
        (OUT / f"{st}.json").write_text(json.dumps(_summ(by_stage.get(st, []), groups), ensure_ascii=False, indent=1), "utf-8")
    _write_summary(overall, by_stage, groups, recent)
    return overall


def _write_summary(overall, by_stage, groups, recent):
    pop = overall["population"]
    lines = [f"# 채용공고 통계 ({overall['generated']}, 백엔드 계열)", "",
             f"> 모집단: **현재 모집 중 {pop['postings']}건** (게시일 티어 {pop['tiers']}). {pop['note']}.",
             f"> 최근 {overall['window_days']}일 신규 게시만 보면 **{recent['postings']}건** — 표본이 작아 동향 해석은 참고만. 조건: {pop['spec']}", "",
             f"- 공고 수: **{overall['postings']}**  · 출처: {overall['by_source']}",
             f"- 코딩테스트 언급 {overall['coding_test_pct']}% · 과제 언급 {overall['assignment_pct']}%",
             f"- 최소 경력 분포(년): {overall['min_years_dist']}", "",
             "## 상위 기술/키워드 (전체)", "", "| 키워드 | 공고 수 | 비율 |", "|---|---:|---:|"]
    lines += [f"| {s['skill']} | {s['count']} | {s['pct']}% |" for s in overall["top_skills"][:25]]
    lines += ["", "## 단계별", ""]
    for st, rows in sorted(by_stage.items(), key=lambda kv: -len(kv[1])):
        s = _summ(rows, groups)
        top = ", ".join(f"{x['skill']} {x['pct']}%" for x in s["top_skills"][:10])
        lines.append(f"- **{st}** ({s['postings']}건, 코테 {s['coding_test_pct']}%, 과제 {s['assignment_pct']}%): {top}")
    if overall["unclassified_companies"]:
        lines += ["", "## 단계 미분류 회사 (companies.yaml에 추가 필요)", ""]
        lines += [f"- {c} ({n})" for c, n in overall["unclassified_companies"][:30]]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", "utf-8")
