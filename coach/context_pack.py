"""Build a compact, model-agnostic context bundle for one review (retrieval instead of dumping everything).

    .venv/bin/python -m coach.context_pack --band growth [--role product_backend] [--uid <job uid>]
                                           [--years 4] [--resume me/resume.md] [--out data/packs/x.json]

Contents (each piece tagged with its provenance so feedback can say where a judgement comes from):
  persona   [통계]   band axis weights (role-adjusted), distinctive/weak axes, process %, red flags, evidence bars
  job       [공고]   the target posting's insight (must/work/nice with verbatim quotes)
  similar   [공고]   must-have quotes from the 5 most similar postings in the same band
  mentor    [멘토]   principles whose applies_when matches (stage/role/years)
  resume              redacted text (PII removed)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import yaml

from crawler import db
from crawler.insight import AXES
from crawler.persona_build import axis_vector, band_of
from crawler.stats import company_stage_map
from crawler.db import _norm
from .redact import redact

ROOT = Path(__file__).resolve().parent.parent
PDIR = ROOT / "data" / "personas"


def _load(name):
    p = PDIR / f"{name}.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def _cos(a, b):
    num = sum(a[k] * b[k] for k in AXES)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0


def _years_ok(spec, years):
    if not spec or years is None:
        return True
    lo, _, hi = str(spec).partition("-")
    return (not lo or years >= int(lo)) and (not hi or years <= int(hi))


def persona_part(band, role):
    p = _load(band) or _load("overall")
    w = dict(p["axis_weight"])
    note = None
    r = _load(f"role_{role}") if role else None
    if r:
        w = {a: w[a] * (r["lift"][a] or 1) for a in AXES}
        s = sum(w.values()) or 1
        w = {a: round(v / s, 3) for a, v in w.items()}
        note = f"role_{role} lift 적용"
    card = PDIR / f"{band}.card.json"
    bars = {}
    if card.exists():
        c = json.loads(card.read_text("utf-8"))
        bars = {a["axis"]: a["evidence_bar"] for a in c.get("axes", [])}
    top = sorted(w, key=lambda a: -w[a])[:6]
    return {
        "_provenance": "통계", "band": p["band"], "postings": p["postings"], "confidence": p["confidence"],
        "axis_weight": w, "weight_note": note, "top_axes": top,
        "distinctive_axes": p["distinctive_axes"], "weak_axes": p["weak_axes"],
        "process_pct": p["process_pct"], "min_years_median": p["min_years_median"],
        "red_flags": [{"flag": f["flag"], "uid": f["uid"]} for f in p["red_flags"][:5]],
        "evidence_bars": {a: bars[a] for a in top if a in bars},
    }


def job_part(con, uid):
    row = con.execute("SELECT j.company, j.title, i.data FROM jobs j JOIN job_insights i ON i.uid=j.uid WHERE j.uid=?",
                      (uid,)).fetchone()
    if not row:
        return None, None
    ins = json.loads(row["data"])
    part = {"_provenance": "공고", "uid": uid, "company": row["company"], "title": row["title"],
            "team_problem": ins["team_problem"], "role_type": ins["role_type"], "domain": ins["domain"],
            "items": [{"kind": i["kind"], "axis": i["axis"], "quote": i["quote"][:140]} for i in ins["items"]],
            "red_flags": ins["red_flags"], "process": ins["process"], "seniority": ins["seniority"]}
    return part, axis_vector(ins)


def similar_part(con, band, ref_vec, exclude_uid=None, k=5):
    stage_of = company_stage_map()
    cands = []
    for r in con.execute("SELECT j.uid, j.company, i.data FROM jobs j JOIN job_insights i ON i.uid=j.uid").fetchall():
        if r["uid"] == exclude_uid:
            continue
        ins = json.loads(r["data"])
        st = stage_of.get(_norm(r["company"])) or (ins.get("stage_hint") or {}).get("value", "unknown")
        if band and band_of(st) != band:
            continue
        cands.append((_cos(ref_vec, axis_vector(ins)) if ref_vec else 0, r["uid"], r["company"], ins))
    cands.sort(key=lambda c: -c[0])
    out = []
    for score, uid, co, ins in cands[:k]:
        musts = [i["quote"][:120] for i in ins["items"] if i["kind"] == "must"][:3]
        out.append({"uid": uid, "company": co, "similarity": round(score, 2), "must": musts})
    return {"_provenance": "공고", "postings": out}


def mentor_part(band, role, years, axes):
    data = yaml.safe_load((ROOT / "mentors" / "principles.yaml").read_text("utf-8"))["principles"]
    keep = []
    for p in data:
        aw = p.get("applies_when") or {}
        stages = aw.get("stages") or ["any"]
        roles = aw.get("roles") or ["any"]
        if "any" not in stages and band not in stages:
            continue
        if "any" not in roles and role not in roles:
            continue
        if not _years_ok(aw.get("years"), years):
            continue
        if p["axis"] in axes or p["axis"] in ("resume_format", "job_search"):
            keep.append({k: p.get(k) for k in ("id", "source", "source_type", "axis", "criterion", "good_example", "bad_example", "check")})
    return {"_provenance": "멘토", "principles": keep}


def build(band, role=None, uid=None, years=None, resume=None):
    con = db.connect()
    persona = persona_part(band, role)
    job, job_vec = job_part(con, uid) if uid else (None, None)
    ref = job_vec or persona["axis_weight"]
    pack = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "request": {"band": band, "role": role, "uid": uid, "years": years},
        "persona": persona,
        "job": job,
        "similar": similar_part(con, band, ref, exclude_uid=uid),
        "mentor": mentor_part(band, role, years, persona["top_axes"]),
    }
    if resume:
        text, counts = redact(Path(resume).read_text("utf-8"))
        pack["resume"] = {"text": text, "redactions": counts}
    pack["approx_tokens"] = len(json.dumps(pack, ensure_ascii=False)) // 3
    return pack


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", required=True, choices=["early", "growth", "late", "bigtech", "mid", "overall"])
    ap.add_argument("--role")
    ap.add_argument("--uid")
    ap.add_argument("--years", type=int)
    ap.add_argument("--resume")
    ap.add_argument("--out")
    a = ap.parse_args()
    pk = build(a.band, a.role, a.uid, a.years, a.resume)
    out = a.out or str(ROOT / "data" / "packs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{a.band}.json")
    Path(out).write_text(json.dumps(pk, ensure_ascii=False, indent=1), "utf-8")
    print(out, "≈", pk["approx_tokens"], "tokens")
