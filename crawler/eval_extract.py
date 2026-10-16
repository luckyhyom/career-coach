"""Measure rule-based extraction accuracy against hand labels.

    .venv/bin/python -m crawler.eval_extract sample --n 30   # -> data/eval/extract_gold.jsonl (gold_* = null, fill in)
    .venv/bin/python -m crawler.eval_extract score           # precision / recall / F1, per-skill errors

Label rules (gold_skills): a skill counts only if the posting asks for or uses it
(requirements, preferred, stack, or work description). Mentions like "AI 시대" without a technical
requirement do not count. Use canonical names from skills_dict.yaml.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from . import db
from .extract import extract_row, load_skill_patterns

GOLD = Path(__file__).resolve().parent.parent / "data" / "eval" / "extract_gold.jsonl"


def sample(n: int, seed: int = 7):
    con = db.connect()
    rows = con.execute("SELECT * FROM jobs WHERE extracted_at IS NOT NULL").fetchall()
    random.Random(seed).shuffle(rows)
    existing = {json.loads(l)["uid"] for l in GOLD.read_text().splitlines()} if GOLD.exists() else set()
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    with GOLD.open("a", encoding="utf-8") as f:
        for r in rows:
            if r["uid"] in existing:
                continue
            f.write(json.dumps({
                "uid": r["uid"], "company": r["company"], "title": r["title"],
                "pred_skills": json.loads(r["skills"] or "[]"), "pred_min_years": r["min_years"],
                "pred_coding_test": r["coding_test"], "pred_assignment": r["assignment"],
                "gold_skills": None, "gold_min_years": None, "gold_coding_test": None, "gold_assignment": None,
                "labeler": None,
            }, ensure_ascii=False) + "\n")
            added += 1
            if added >= n:
                break
    print(f"added {added} rows to {GOLD} — fill gold_* fields (see module docstring for rules)")


def score():
    patterns = load_skill_patterns()
    con = db.connect()
    items = [json.loads(l) for l in GOLD.read_text().splitlines() if l.strip()]
    items = [i for i in items if i.get("gold_skills") is not None]
    if not items:
        print("no labeled rows yet")
        return
    tp = fp = fn = 0
    fp_by, fn_by = Counter(), Counter()
    years_ok = ct_ok = as_ok = 0
    for it in items:
        row = con.execute("SELECT * FROM jobs WHERE uid=?", (it["uid"],)).fetchone()
        if row is None:
            continue
        pred = extract_row(row, patterns)  # re-extract with the current dictionary
        p, g = set(json.loads(pred["skills"])), set(it["gold_skills"])
        tp += len(p & g); fp += len(p - g); fn += len(g - p)
        fp_by.update(p - g); fn_by.update(g - p)
        years_ok += int(pred["min_years"] == it["gold_min_years"])
        ct_ok += int(pred["coding_test"] == it["gold_coding_test"])
        as_ok += int(pred["assignment"] == it["gold_assignment"])
    n = len(items)
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    report = {
        "labeled": n, "skills_precision": round(prec, 3), "skills_recall": round(rec, 3), "skills_f1": round(f1, 3),
        "min_years_acc": round(years_ok / n, 3), "coding_test_acc": round(ct_ok / n, 3), "assignment_acc": round(as_ok / n, 3),
        "top_false_positives": fp_by.most_common(10), "top_false_negatives": fn_by.most_common(10),
        "labelers": dict(Counter(i.get("labeler") for i in items)),
        # independent = labeled by someone other than the model that also tuned the rules
        "independent_labels": sum(1 for i in items if not str(i.get("labeler") or "").startswith("claude")),
        "status": "preliminary — labels by Claude, rules tuned on the same sample; needs user-verified / held-out labels"
                  if all(str(i.get("labeler") or "").startswith("claude") for i in items) else "includes independent labels",
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    (GOLD.parent / "extract_score.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "score"])
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    sample(a.n) if a.cmd == "sample" else score()
