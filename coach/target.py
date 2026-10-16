"""Stage fit from a candidate profile (deterministic): which company stage band suits this resume now.

fit(band) = 100 * Σ axis_weight[band][a] * level[a]/3   - seniority penalty   (+ notes on red flags / process)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDIR = ROOT / "data" / "personas"
BANDS = ["early", "growth", "late", "bigtech", "mid"]


def fit(levels: dict, years) -> list:
    out = []
    for b in BANDS:
        p = PDIR / f"{b}.json"
        if not p.exists():
            continue
        prof = json.loads(p.read_text("utf-8"))
        w = prof["axis_weight"]
        raw = 100 * sum(w[a] * levels.get(a, 0) / 3 for a in w)
        need = prof.get("min_years_median")
        penalty = 0.0
        if need is not None and years is not None and years < need:
            penalty = min(15.0, 5.0 * (need - years))
        gaps = sorted(w, key=lambda a: -(w[a] * (3 - levels.get(a, 0))))[:3]  # biggest weighted gaps
        out.append({"band": b, "fit": round(raw - penalty, 1), "raw": round(raw, 1), "seniority_penalty": round(penalty, 1),
                    "confidence": prof["confidence"], "companies": prof["companies"], "top_gaps": gaps,
                    "process_pct": prof.get("process_pct", {})})
    return sorted(out, key=lambda x: -x["fit"])
