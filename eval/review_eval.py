"""Compare models on the same resume + same context (quality, consistency, cost, latency).

    .venv/bin/python -m eval.review_eval --models claude-haiku,claude-sonnet --repeats 2 [--cases eval/cases]

Per case (eval/cases/*.yaml): resume file, band/role/uid/years, and mentor_gold = key problems a real mentor found.
Metrics (5 criteria from the plan + cost/latency):
  1 정확성     hallucination_rate (deterministic: quote/evidence/number checks)          [auto]
  2 문제 발견   mentor_recall = gold issues found / gold issues (LLM judge, human-verifiable) [auto-judge]
  3 실용성     practicality 1-5 (LLM judge)                                              [auto-judge → 사람 채점 시트]
  4 직무 적합성 job_relevance 1-5 (LLM judge)                                             [auto-judge → 사람 채점 시트]
  5 일관성     axis score stdev across repeats + gold-match agreement across repeats      [auto]
The high-end model is NOT treated as ground truth; mentor_gold is. Until real mentor labels exist,
cases marked gold_source=provisional are only for pipeline testing.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path

import yaml

from coach.context_pack import build
from coach.llm import complete
from coach.review import review

ROOT = Path(__file__).resolve().parent.parent
JUDGE = "claude-sonnet"
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {"type": "array", "items": {"type": "object", "properties": {
            "gold_id": {"type": "string"}, "found": {"type": "boolean"}, "issue_index": {"type": ["integer", "null"]}},
            "required": ["gold_id", "found", "issue_index"]}},
        "practicality": {"type": "integer", "minimum": 1, "maximum": 5},
        "job_relevance": {"type": "integer", "minimum": 1, "maximum": 5},
        "comment": {"type": "string"},
    },
    "required": ["matches", "practicality", "job_relevance", "comment"],
}
JUDGE_SYSTEM = """너는 이력서 피드백 평가자다. 입력: 멘토가 찾은 핵심 문제 목록(gold)과 모델 피드백(issues).
- 각 gold 문제를 모델 issues 중 하나가 실질적으로 같은 문제를 지적했는지 판정한다(표현이 달라도 같은 문제면 found).
- practicality(1~5): 수정안을 사용자가 그대로 적용할 수 있는가.
- job_relevance(1~5): 백엔드 채용에서 중요한 순서로 우선순위를 잡았는가.
JSON만 출력."""


def run_case(case, models, repeats):
    resume_path = str(ROOT / case["resume_file"])
    pack = build(case["band"], case.get("role"), case.get("uid"), case.get("years"), resume_path)
    rows = []
    for m in models:
        runs = []
        for k in range(repeats):
            r = review(pack, m)
            j = complete(JUDGE, JUDGE_SYSTEM, json.dumps({"gold": case["mentor_gold"], "issues": r["result"].get("issues", [])},
                                                         ensure_ascii=False), JUDGE_SCHEMA)["json"] or {}
            found = {x["gold_id"] for x in j.get("matches", []) if x.get("found")}
            runs.append({"r": r, "j": j, "found": found})
        scores = {}
        for run in runs:
            for s in run["r"]["result"].get("axis_scores", []):
                scores.setdefault(s["axis"], []).append(s["score"])
        stdev = statistics.mean([statistics.pstdev(v) for v in scores.values()]) if scores else None
        sets = [x["found"] for x in runs]
        agree = (len(set.intersection(*sets)) / len(set.union(*sets))) if sets and set.union(*sets) else None
        g = len(case["mentor_gold"]) or 1
        rows.append({
            "case": case["id"], "model": m, "repeats": repeats, "gold_source": case.get("gold_source"),
            "hallucination_rate": round(statistics.mean(x["r"]["validation"]["hallucination_rate"] for x in runs), 3),
            "pass_rate": round(statistics.mean(x["r"]["validation"]["pass_rate"] for x in runs), 3),
            "mentor_recall": round(statistics.mean(len(x["found"]) / g for x in runs), 3),
            "practicality": round(statistics.mean(x["j"].get("practicality", 0) for x in runs), 2),
            "job_relevance": round(statistics.mean(x["j"].get("job_relevance", 0) for x in runs), 2),
            "score_stdev": round(stdev, 2) if stdev is not None else None,
            "gold_agreement": round(agree, 2) if agree is not None else None,
            "cost_usd": round(sum(x["r"]["cost_usd"] or 0 for x in runs) / repeats, 4),
            "latency_s": round(statistics.mean(x["r"]["latency_s"] for x in runs), 1),
            "tokens_in": int(statistics.mean(x["r"]["usage"]["input"] for x in runs)),
            "tokens_out": int(statistics.mean(x["r"]["usage"]["output"] for x in runs)),
            "_runs": [{"issues": x["r"]["result"].get("issues"), "validation": x["r"]["validation"], "judge": x["j"]} for x in runs],
        })
    return rows, pack["approx_tokens"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="claude-haiku,claude-sonnet")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--cases", default=str(ROOT / "eval" / "cases"))
    a = ap.parse_args()
    models = a.models.split(",")
    allrows = []
    for f in sorted(Path(a.cases).glob("*.yaml")):
        case = yaml.safe_load(f.read_text("utf-8"))
        rows, ptoks = run_case(case, models, a.repeats)
        allrows += rows
    stamp = time.strftime("%Y%m%d-%H%M")
    out = ROOT / "eval" / "results"
    (out / f"{stamp}.json").write_text(json.dumps(allrows, ensure_ascii=False, indent=1), "utf-8")
    cols = ["case", "model", "hallucination_rate", "pass_rate", "mentor_recall", "practicality", "job_relevance",
            "score_stdev", "gold_agreement", "cost_usd", "latency_s", "tokens_in", "tokens_out", "gold_source"]
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in allrows]
    (out / f"{stamp}.md").write_text("# 모델 비교\n\n" + "\n".join(md) + "\n\n- hallucination_rate·pass_rate: 결정적 검증 / mentor_recall·practicality·job_relevance: LLM 심판(사람 채점으로 교체 권장)\n", "utf-8")
    with (out / f"{stamp}_human.csv").open("w", newline="", encoding="utf-8") as fh:  # sheet for a real mentor
        w = csv.writer(fh)
        w.writerow(["case", "model", "repeat", "정확성(1-5)", "문제발견(1-5)", "실용성(1-5)", "직무적합성(1-5)", "일관성(1-5)", "메모"])
        for r in allrows:
            for k in range(r["repeats"]):
                w.writerow([r["case"], r["model"], k + 1, "", "", "", "", "", ""])
    print("\n".join(md))
    print(f"\nsaved eval/results/{stamp}.json/.md/_human.csv")


if __name__ == "__main__":
    main()
