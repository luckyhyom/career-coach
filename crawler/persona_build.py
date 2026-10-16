"""Build data-driven persona profiles from job_insights (deterministic, no LLM).

    .venv/bin/python -m crawler.persona_build     # -> data/personas/<band>.json, _matrix.json, _matrix.md

- Stage band of a posting: companies.yaml stage > insight stage_hint (quote-verified) > unknown
- Axis weight per posting: must 1.0 / work 0.7 / nice 0.5, normalized per posting (sum=1), averaged per band
- Shrinkage toward the overall profile for small bands: w = n/(n+K)*band + K/(n+K)*overall  (K=15)
- lift = band weight / overall weight; only lift >= 1.2 traits are "distinctive"
- Pairwise cosine similarity; bands above 0.95 are flagged as not distinct (merge candidates)
"""
from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from . import db
from .adapters.common import RoleFilter
from .db import _norm
from .insight import AXES
from .stats import company_stage_map

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "personas"
K = 5          # shrinkage strength, in *companies*
WEIGHT = {"must": 1.0, "work": 0.7, "nice": 0.5}
BANDS = {
    "early": {"seed", "series_a"},
    "growth": {"series_b", "series_c_plus"},
    "late": {"pre_ipo_unicorn", "foreign"},
    "bigtech": {"big_tech", "enterprise"},
    "mid": {"listed_mid", "si_agency"},
}
ROLE_TYPES = ["product_backend", "platform_backend", "fullstack", "sdet_quality", "devops_sre"]
ABROAD = re.compile(r"usa|united states|india|bengaluru|hyderabad|singapore|china|shanghai|taiwan|taipei|japan|tokyo|"
                    r"seattle|mountain view|new york|nyc|london|vietnam|hanoi", re.I)


def band_of(stage: str):
    return next((b for b, s in BANDS.items() if stage in s), None)


def axis_vector(ins) -> dict:
    v = defaultdict(float)
    for it in ins["items"]:
        v[it["axis"]] += WEIGHT.get(it["kind"], 0.5)
    tot = sum(v.values()) or 1
    return {a: v[a] / tot for a in AXES}


def mean_vec(vecs):
    if not vecs:
        return {a: 0.0 for a in AXES}
    return {a: sum(v[a] for v in vecs) / len(vecs) for a in AXES}


def cosine(a, b):
    num = sum(a[k] * b[k] for k in AXES)
    den = math.sqrt(sum(a[k] ** 2 for k in AXES)) * math.sqrt(sum(b[k] ** 2 for k in AXES))
    return num / den if den else 0


def load():
    con = db.connect()
    stage_of = company_stage_map()
    rf = RoleFilter([], [])
    recs = []
    for r in con.execute("SELECT j.*, i.data AS ins FROM jobs j JOIN job_insights i ON i.uid=j.uid").fetchall():
        if ABROAD.search(r["location"] or "") or rf.excluded(r["title"]):
            continue
        ins = json.loads(r["ins"])
        stage, src = stage_of.get(_norm(r["company"])), "companies.yaml"
        if not stage or stage == "unknown":
            hint = (ins.get("stage_hint") or {}).get("value", "unknown")
            stage, src = (hint, "posting_hint") if hint != "unknown" else ("unknown", None)
        recs.append({"uid": r["uid"], "company": r["company"], "title": r["title"], "ins": ins,
                     "stage": stage, "stage_src": src, "band": band_of(stage), "vec": axis_vector(ins)})
    return recs


def company_balanced(recs):
    """Average per company first, then across companies, so one heavy poster can't define a band."""
    by_co = defaultdict(list)
    for r in recs:
        by_co[r["company"]].append(r["vec"])
    return mean_vec([mean_vec(v) for v in by_co.values()]), len(by_co)


def profile(recs, overall_vec, name):
    n_post = len(recs)
    raw, n = company_balanced(recs)  # n = number of companies (effective sample)
    shrunk = {a: (n / (n + K)) * raw[a] + (K / (n + K)) * overall_vec[a] for a in AXES}
    lift = {a: round(shrunk[a] / overall_vec[a], 2) if overall_vec[a] else None for a in AXES}

    def quotes(axis, kinds=("must", "work"), limit=6):
        out, seen_co = [], Counter()
        for r in recs:
            for it in r["ins"]["items"]:
                if it["axis"] == axis and it["kind"] in kinds and seen_co[r["company"]] < 1:
                    out.append({"kind": it["kind"], "quote": it["quote"], "gist": it["gist"], "uid": r["uid"], "company": r["company"]})
                    seen_co[r["company"]] += 1
                    break
            if len(out) >= limit:
                break
        return out

    proc = Counter()
    for r in recs:
        for k, v in r["ins"]["process"].items():
            proc[k] += int(bool(v))
    years = [r["ins"]["seniority"]["min_years"] for r in recs if r["ins"]["seniority"]["min_years"] is not None]
    return {
        "band": name,
        "postings": n_post,
        "companies": n,
        "confidence": "high" if n >= 15 else "medium" if n >= 6 else "low",
        "weighting": "company-balanced (회사별 평균 후 회사 간 평균), shrinkage K=5 companies",
        "top_company_share": round(max(Counter(r["company"] for r in recs).values()) / n_post, 2) if n_post else 0,
        "axis_weight_raw": {a: round(raw[a], 3) for a in AXES},
        "axis_weight": {a: round(shrunk[a], 3) for a in AXES},
        "lift": lift,
        "distinctive_axes": sorted([a for a in AXES if lift[a] and lift[a] >= 1.2], key=lambda a: -lift[a]),
        "weak_axes": sorted([a for a in AXES if lift[a] and lift[a] <= 0.8], key=lambda a: lift[a]),
        "axis_quotes": {a: quotes(a) for a in AXES},
        "nice_quotes": {a: quotes(a, ("nice",), 3) for a in AXES},
        "red_flags": [{"flag": f["flag"], "quote": f["quote"], "uid": r["uid"], "company": r["company"]}
                      for r in recs for f in r["ins"]["red_flags"]][:25],
        "process_pct": {k: round(100 * v / n_post, 1) for k, v in proc.items()} if n_post else {},
        "min_years_median": statistics.median(years) if years else None,
        "scope": dict(Counter(r["ins"]["seniority"]["scope"] for r in recs)),
        "product_maturity": dict(Counter(r["ins"]["product_maturity"] for r in recs).most_common()),
        "hiring_reason": dict(Counter(r["ins"]["hiring_reason"] for r in recs).most_common()),
        "domains": Counter(r["ins"]["domain"] for r in recs).most_common(12),
        "role_types": dict(Counter(r["ins"]["role_type"] for r in recs).most_common()),
        "stack_flexibility": dict(Counter(r["ins"]["stack_flexibility"] for r in recs)),
        "team_problems": [{"text": r["ins"]["team_problem"], "uid": r["uid"], "company": r["company"]} for r in recs[:20]],
        "work_items_for_questions": [{"quote": it["quote"], "uid": r["uid"]} for r in recs for it in r["ins"]["items"]
                                     if it["kind"] == "work"][:40],
        "companies_list": Counter(r["company"] for r in recs).most_common(30),
    }


def run():
    recs = load()
    OUT.mkdir(parents=True, exist_ok=True)
    overall, _ = company_balanced(recs)
    groups = {"overall": recs}
    for b in BANDS:
        groups[b] = [r for r in recs if r["band"] == b]
    for rt in ROLE_TYPES:
        groups[f"role_{rt}"] = [r for r in recs if r["ins"]["role_type"] == rt]
    profiles = {name: profile(rs, overall, name) for name, rs in groups.items()}
    for name, p in profiles.items():
        (OUT / f"{name}.json").write_text(json.dumps(p, ensure_ascii=False, indent=1), "utf-8")

    bands = [b for b in BANDS if profiles[b]["postings"] > 0]
    sim = {f"{a}~{b}": round(cosine(profiles[a]["axis_weight_raw"], profiles[b]["axis_weight_raw"]), 3)
           for i, a in enumerate(bands) for b in bands[i + 1:]}
    matrix = {
        "postings_total": len(recs),
        "stage_resolution": dict(Counter(r["stage_src"] or "unresolved" for r in recs)),
        "band_counts": {b: profiles[b]["postings"] for b in BANDS},
        "unknown_stage_postings": sum(1 for r in recs if r["band"] is None),
        "lift_table": {b: profiles[b]["lift"] for b in BANDS},
        "similarity": sim,
        "merge_candidates": [k for k, v in sim.items() if v > 0.95],
        "unknown_companies": Counter(r["company"] for r in recs if r["band"] is None).most_common(60),
    }
    (OUT / "_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=1), "utf-8")
    _write_md(profiles, matrix)
    return matrix


def _write_md(profiles, m):
    ax = list(AXES)
    L = [f"# 페르소나 매트릭스 (공고 {m['postings_total']}건, 단계 미확인 {m['unknown_stage_postings']}건)", "",
         f"단계 판정 근거: {m['stage_resolution']}", "",
         "## 축 가중치 lift (전체 평균 = 1.0, 회사 균형 가중 + 축소추정 K=5개사)", "",
         "| 축 | " + " | ".join(f"{b} ({profiles[b]['companies']}개사/{profiles[b]['postings']}건, {profiles[b]['confidence']})" for b in BANDS) + " |",
         "|---|" + "---:|" * len(BANDS)]
    for a in ax:
        L.append(f"| {a} | " + " | ".join(f"**{profiles[b]['lift'][a]}**" if (profiles[b]['lift'][a] or 0) >= 1.2
                                           else str(profiles[b]['lift'][a]) for b in BANDS) + " |")
    L += ["", "## 단계 간 유사도 (코사인, raw 가중치)", ""] + [f"- {k}: {v}" for k, v in m["similarity"].items()]
    L += ["", f"병합 후보(>0.95): {m['merge_candidates'] or '없음'}", "", "## 직무 유형별 특징 축 (lift≥1.2)", ""]
    for rt in ROLE_TYPES:
        p = profiles[f"role_{rt}"]
        feats = ", ".join("%s %s" % (a, p["lift"][a]) for a in p["distinctive_axes"]) or "-"
        L.append(f"- **{rt}** (n={p['postings']}): {feats}")
    (OUT / "_matrix.md").write_text("\n".join(L) + "\n", "utf-8")


if __name__ == "__main__":
    print(json.dumps({k: v for k, v in run().items() if k != "unknown_companies"}, ensure_ascii=False, indent=1)[:3000])
