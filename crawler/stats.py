"""Aggregate stats per company stage -> data/stats/*.json (+ summary.md). No LLM."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import db
from .db import _norm
from .extract import load_skill_patterns

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
    }


def run(days: int = 30, max_years: int = 7) -> dict:
    con = db.connect()
    stage_of = company_stage_map()
    groups = {name: g for name, (g, _) in load_skill_patterns().items()}
    since = (date.today() - timedelta(days=days)).isoformat()
    # active = seen in this window (open now) and either posted recently or always-hiring
    rows = con.execute(
        "SELECT * FROM jobs WHERE extracted_at IS NOT NULL AND substr(last_seen,1,10) >= ? "
        "AND (always_hiring=1 OR posted_at IS NULL OR posted_at >= ?) "
        "AND (min_years IS NULL OR min_years <= ?)",
        (since, since, max_years),
    ).fetchall()
    by_stage = defaultdict(list)
    unknown = Counter()
    for r in rows:
        st = stage_of.get(_norm(r["company"]), "unknown")
        by_stage[st].append(r)
        if st == "unknown":
            unknown[r["company"]] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    overall = _summ(rows, groups)
    overall["by_source"] = dict(Counter(r["source"] for r in rows))
    overall["by_stage"] = {s: len(by_stage.get(s, [])) for s in STAGES}
    overall["unclassified_companies"] = unknown.most_common(50)
    overall["window_days"] = days
    overall["generated"] = date.today().isoformat()
    (OUT / "overall.json").write_text(json.dumps(overall, ensure_ascii=False, indent=1), "utf-8")
    for st in STAGES:
        (OUT / f"{st}.json").write_text(json.dumps(_summ(by_stage.get(st, []), groups), ensure_ascii=False, indent=1), "utf-8")
    _write_summary(overall, by_stage, groups)
    return overall


def _write_summary(overall, by_stage, groups):
    lines = [f"# 채용공고 통계 ({overall['generated']}, 최근 {overall['window_days']}일, 백엔드 계열)", "",
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
