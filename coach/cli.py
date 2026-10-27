"""Engine CLI — works for any candidate with just a resume. No Claude Code required.

    # 이력서만 (단계 자동 선택)
    .venv/bin/python -m coach.cli review --resume path/to/resume.md
    # 프로필 폴더 (결과는 <profile>/reviews/ 에 저장)
    .venv/bin/python -m coach.cli review --profile profiles/me --band growth --role product_backend
    # 특정 공고 기준
    .venv/bin/python -m coach.cli review --profile profiles/me --job <uid>
    # 단계 적합도만
    .venv/bin/python -m coach.cli target --resume path/to/resume.md
    # 모델 바꾸기: --model <models.yaml 이름>  또는  COACH_MODEL_REVIEW=local-qwen-small
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

from .candidate import levels, parse
from .context_pack import build
from .report import render, to_json
from .review import review
from .target import fit as stage_fit

ROOT = Path(__file__).resolve().parent.parent


def _resume_path(a):
    if a.resume:
        return Path(a.resume)
    prof = Path(a.profile or os.environ.get("COACH_PROFILE", "profiles/me"))
    path = prof / "resume.md" if prof.is_absolute() else ROOT / prof / "resume.md"
    if not path.exists():
        raise SystemExit(f"{path} not found. Pass --resume <file>, or: cp -r profiles/_template profiles/me "
                         f"(or set COACH_PROFILE in .env)")
    return path


def _job_band(uid):
    from crawler.population import resolve_stage
    from crawler.persona_build import band_of
    con = sqlite3.connect(ROOT / "data" / "jobs.sqlite")
    r = con.execute("SELECT j.company, i.data FROM jobs j LEFT JOIN job_insights i ON i.uid=j.uid WHERE j.uid=?", (uid,)).fetchone()
    if not r:
        raise SystemExit(f"job {uid} not found")
    st, _ = resolve_stage(r[0], json.loads(r[1]) if r[1] else None)
    return band_of(st)


def _fresh(a):
    """Re-crawl first when the posting data is older than today (crawler/refresh.py)."""
    from crawler.refresh import ensure_fresh
    d = ensure_fresh(not a.no_refresh)
    return d.isoformat() if d else None


def cmd_target(a):
    text = _resume_path(a).read_text("utf-8")
    _fresh(a)
    prof = parse(text)
    res = stage_fit(levels(prof), prof.get("years_total"))
    print(json.dumps({"candidate": {k: prof[k] for k in ("years_total", "role_types", "domains")}, "fit": res},
                     ensure_ascii=False, indent=1))


def cmd_review(a):
    rpath = _resume_path(a)
    text = rpath.read_text("utf-8")
    as_of = _fresh(a)
    prof = parse(text)
    fit = stage_fit(levels(prof), prof.get("years_total"))
    band = a.band or (_job_band(a.job) if a.job else None) or (fit[0]["band"] if fit else "overall")
    role = a.role or next((r for r in prof.get("role_types", []) if r in
                           ("product_backend", "platform_backend", "fullstack", "sdet_quality", "devops_sre")), None)
    pack = build(band, role, a.job, int(prof["years_total"]) if prof.get("years_total") else None, str(rpath))
    r = review(pack, a.model or "route:review")
    meta = {"candidate": a.name or rpath.parent.name, "created": time.strftime("%Y-%m-%d %H:%M"), "model": r["model"],
            "cost_usd": (r["cost_usd"] or 0) + (prof["_meta"].get("cost_usd") or 0), "latency_s": r["latency_s"],
            "band_selected": "manual" if a.band else ("job" if a.job else "auto"), "data_as_of": as_of}
    md = render(r["result"], r["validation"], pack, meta, fit if not a.band else None)
    out_dir = Path(a.out) if a.out else (rpath.parent / "reviews" if (rpath.parent / "reviews").exists() else ROOT / "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{time.strftime('%Y%m%d-%H%M')}-review-{band}" + (f"-{a.job}" if a.job else "")
    (out_dir / f"{stem}.md").write_text(md, "utf-8")
    (out_dir / f"{stem}.json").write_text(to_json(r["result"], r["validation"], pack, meta, fit), "utf-8")
    print(f"saved {out_dir / stem}.md  (band={band}, role={role}, pass_rate={r['validation']['pass_rate']:.0%})")


def cmd_panel(a):
    from .panel import render as prender, run as prun
    rpath = _resume_path(a)
    as_of = _fresh(a)
    out_dir = Path(a.out) if a.out else (rpath.parent / "reviews" if (rpath.parent / "reviews").exists() else ROOT / "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    prev_files = sorted(out_dir.glob("*-panel.json"))
    previous = json.loads(prev_files[-1].read_text("utf-8"))["panel"] if prev_files else None
    panel, agg, meta = prun(rpath.read_text("utf-8"), a.name or rpath.parent.name, a.model or "route:review", previous)
    meta["data_as_of"] = as_of
    stem = f"{time.strftime('%Y%m%d-%H%M')}-panel"
    (out_dir / f"{stem}.md").write_text(prender(panel, agg, meta), "utf-8")
    (out_dir / f"{stem}.json").write_text(json.dumps({"meta": meta, "panel": [{k: v for k, v in p.items() if k != "vec"} for p in panel],
                                                      "aggregate": agg}, ensure_ascii=False, indent=1), "utf-8")
    print(f"saved {out_dir / stem}.md  seats={agg['seats']}  verdicts={[p['result']['verdict'] for p in panel if p['result']]}")


def main():
    from .llm import _env
    _env()  # .env: COACH_PROFILE, model overrides, API keys
    ap = argparse.ArgumentParser(prog="coach")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("review", "target", "panel"):
        p = sub.add_parser(name)
        p.add_argument("--resume")
        p.add_argument("--profile")
        p.add_argument("--no-refresh", action="store_true", help="skip the automatic re-crawl when posting data is older than today")
        if name == "panel":
            p.add_argument("--model")
            p.add_argument("--name")
            p.add_argument("--out")
        if name == "review":
            p.add_argument("--band", choices=["early", "growth", "late", "bigtech", "mid", "overall"])
            p.add_argument("--role")
            p.add_argument("--job")
            p.add_argument("--model")
            p.add_argument("--name")
            p.add_argument("--out")
    a = ap.parse_args()
    {"review": cmd_review, "target": cmd_target, "panel": cmd_panel}[a.cmd](a)


if __name__ == "__main__":
    main()
