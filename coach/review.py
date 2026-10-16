"""Model-agnostic resume review: one LLM call on a context pack + deterministic validation (no LLM).

    .venv/bin/python -m coach.review --pack data/packs/x.json --model claude-haiku

This is the service-shaped core (the Claude Code /resume-review skill is the richer local version).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from crawler.insight import AXES
from .llm import complete

EVIDENCE_TYPES = ["공고", "통계", "멘토", "단계추정", "의견"]
SCHEMA = {
    "type": "object",
    "properties": {
        "axis_scores": {"type": "array", "items": {"type": "object", "properties": {
            "axis": {"type": "string", "enum": list(AXES)}, "score": {"type": "integer", "minimum": 0, "maximum": 5},
            "reason": {"type": "string"}}, "required": ["axis", "score", "reason"]}},
        "issues": {"type": "array", "items": {"type": "object", "properties": {
            "resume_quote": {"type": "string", "description": "이력서 원문 그대로"},
            "problem": {"type": "string"},
            "fix": {"type": "string", "description": "바로 쓸 수 있는 대체 문장. 모르는 수치는 [측정값]"},
            "evidence_type": {"type": "string", "enum": EVIDENCE_TYPES},
            "evidence": {"type": "string", "description": "공고면 원문+uid, 통계면 수치, 멘토면 principle id"},
            "severity": {"type": "string", "enum": ["high", "medium", "low"]}},
            "required": ["resume_quote", "problem", "fix", "evidence_type", "evidence", "severity"]}},
        "biggest_lever": {"type": "string"},
        "summary": {"type": "array", "items": {"type": "string"}, "description": "핵심 판정 3줄"},
        "levers": {"type": "array", "description": "우선 개선 3가지(효과 큰 순)", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "why": {"type": "string", "description": "근거 태그 포함"},
            "how": {"type": "string", "description": "구체적 실행(어느 bullet을 어떻게)"},
            "axis": {"type": "string", "enum": list(AXES)}}, "required": ["title", "why", "how", "axis"]}},
        "interview_questions": {"type": "array", "items": {"type": "object", "properties": {
            "q": {"type": "string"}, "follow_up": {"type": "string"},
            "based_on": {"type": "string", "description": "이력서 원문 또는 공고 uid"}},
            "required": ["q", "follow_up", "based_on"]}},
        "job_match": {"type": "array", "description": "job이 주어졌을 때만: job.items 중 must 항목별 판정",
                      "items": {"type": "object", "properties": {
                          "requirement_quote": {"type": "string"}, "status": {"type": "string", "enum": ["met", "partial", "missing"]},
                          "resume_evidence": {"type": "string"}, "gap_type": {"type": "string", "enum": ["real_gap", "ignorable", "none"]}},
                          "required": ["requirement_quote", "status", "resume_evidence", "gap_type"]}},
    },
    "required": ["axis_scores", "issues", "biggest_lever", "summary", "levers", "interview_questions", "job_match"],
}

SYSTEM = """너는 백엔드 이력서 평가자다. 입력은 JSON 컨텍스트 팩(persona=단계 통계, job=대상 공고, similar=유사 공고 필수요건, mentor=멘토 원칙, resume=이력서)이다.
규칙:
1. persona.top_axes 각각을 0~5점: 0 없음/1 키워드만/2 행동만/3 결과 수치/4 수치+측정방법+본인역할/5 4+의사결정 근거. evidence_bars가 있으면 그 단계 기준을 따른다. 의심되면 낮게.
2. issues는 5~10개, severity high부터. 각 issue는 resume_quote(이력서 원문 그대로), problem, fix(그 문장에 맞춘 대체 문장), evidence_type, evidence를 모두 갖춘다.
3. evidence_type: 공고(job/similar의 원문 quote를 그대로+uid) / 통계(persona 수치) / 멘토(mentor principle id) / 단계추정(통계로부터의 추론, 단정 금지) / 의견.
4. 이력서에 없는 경험·수치를 만들지 않는다. 모르는 값은 [측정값].
5. "수치를 넣으세요" 같은 일반론 금지. 약점(high/medium) 최소 3개. 근거 없는 칭찬 금지.
6. summary 3줄, levers 3개(효과 큰 순, why에 근거 태그), interview_questions 5개(이력서 문장이나 공고에서 파생, 꼬리질문 포함).
7. job이 있으면 job_match에 must 항목마다 met/partial/missing과 이력서 근거, gap_type(필수 미충족=real_gap). job이 없으면 빈 배열.
8. 한국어."""


def _norm(s):
    return re.sub(r"\s+", "", s or "").lower()


def validate(result: dict, pack: dict) -> dict:
    resume = pack.get("resume", {}).get("text", "")
    pack_text = _norm(json.dumps({k: pack.get(k) for k in ("job", "similar", "persona")}, ensure_ascii=False))
    mentor_ids = {p["id"] for p in pack.get("mentor", {}).get("principles", [])}
    nres = _norm(resume)
    # a "fact number" = number with a unit (14%, 240ms, 1,000건, 3배 ...). Ordinals / metric names (p95, 1차, 2단계, v2) are not facts.
    NUM = re.compile(r"(?<![A-Za-z0-9.,])(\d[\d,]*(?:\.\d+)?)\s*(%|ms|초|분|시간|건|배|만|억|천|개|명|회|일|x|X|TPS|tps|rps|RPS|GB|MB|KB|원|달러)")
    resume_nums = {m.group(1).replace(",", "") for m in NUM.finditer(resume)}
    checks = []
    for i, it in enumerate(result.get("issues", [])):
        fails = []
        parts = [q for q in re.split(r"\s+/\s+|\n|…|\.\.\.", it["resume_quote"]) if q.strip(" #-•")]  # quotes stitched from several lines
        if not parts or any(_norm(q.strip(" #-•"))[:50] not in nres for q in parts):
            fails.append("quote_not_in_resume")
        et, ev = it["evidence_type"], it.get("evidence", "")
        if et == "공고":
            m = re.search(r'["“\'‘「](.+?)["”\'’」]', ev)
            if not m or _norm(m.group(1))[:40] not in pack_text:
                fails.append("job_quote_not_in_pack")
        if et == "멘토" and not any(mid in ev for mid in mentor_ids):
            fails.append("mentor_id_unknown")
        new_nums = {m.group(1).replace(",", "") for m in NUM.finditer(re.sub(r"\[측정값\]", "", it["fix"]))} - resume_nums
        if new_nums:
            fails.append(f"invented_numbers:{sorted(new_nums)[:3]}")
        if et in ("단계추정", "의견") and re.search(r"반드시|무조건|탈락", it["problem"]):
            fails.append("overclaim")
        checks.append({"i": i, "fails": fails})
    issues = result.get("issues", [])
    n = len(issues) or 1
    mix = {t: sum(1 for x in issues if x["evidence_type"] == t) for t in EVIDENCE_TYPES}
    return {
        "pass_rate": round(sum(1 for c in checks if not c["fails"]) / n, 3),
        "hallucination_rate": round(sum(1 for c in checks if any(f.startswith(("quote_not", "job_quote", "mentor_id", "invented")) for f in c["fails"])) / n, 3),
        "weakness_ok": sum(1 for x in issues if x["severity"] in ("high", "medium")) >= 3,
        "source_mix": mix, "checks": checks,
    }


def review(pack: dict, model: str = "route:review") -> dict:
    user = json.dumps({k: pack[k] for k in ("persona", "job", "similar", "mentor", "resume") if pack.get(k)}, ensure_ascii=False)
    out = complete(model, SYSTEM, user, SCHEMA)
    result = out["json"] or {"axis_scores": [], "issues": [], "biggest_lever": "", "summary": [], "levers": [],
                              "interview_questions": [], "job_match": []}
    return {"model": out["model"], "result": result, "validation": validate(result, pack),
            "usage": out["usage"], "cost_usd": out["cost_usd"], "latency_s": out["latency_s"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--model", default="claude-haiku")
    a = ap.parse_args()
    r = review(json.loads(Path(a.pack).read_text("utf-8")), a.model)
    print(json.dumps(r, ensure_ascii=False, indent=1))
