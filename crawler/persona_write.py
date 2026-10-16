"""Write persona cards from data/personas/<band>.json (LLM, structured output) and validate citations.

    .venv/bin/python -m crawler.persona_write [--bands early,growth,...] [--model sonnet]

The model only interprets the computed profile. Every claim must cite uids present in the profile;
uncited/invalid ones are dropped. Rendering to markdown is deterministic.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .insight import AXES, CLAUDE
from .persona_build import BANDS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "personas"
OUT = ROOT / "personas"
ORDER = ["early", "growth", "late", "bigtech", "mid"]
LABEL = {"early": "초기 스타트업 (시드~시리즈 A)", "growth": "성장기 스타트업 (시리즈 B~C)",
         "late": "후기 스타트업·유니콘 (프리IPO·글로벌 스케일업)", "bigtech": "대기업·빅테크", "mid": "중견·상장사·SI"}

SCHEMA = {
    "type": "object",
    "properties": {
        "one_liner": {"type": "string", "description": "이 단계 면접관이 결국 확인하려는 것 한 문장"},
        "context": {"type": "string", "description": "이 단계 팀의 상황(제품 성숙도·채용 이유·도메인 분포 수치 인용) 2~3문장"},
        "axes": {"type": "array", "description": "distinctive_axes 전부 + 가중치 상위 축으로 최대 6개",
                 "items": {"type": "object", "properties": {
                     "axis": {"type": "string", "enum": list(AXES)},
                     "what_they_look_for": {"type": "string", "description": "공고 인용에 근거한 구체적 기대"},
                     "evidence_bar": {"type": "object", "properties": {k: {"type": "string"} for k in ["2", "3", "4", "5"]},
                                      "required": ["2", "3", "4", "5"],
                                      "description": "이 단계에서 해당 축의 점수별 증거 기준(이력서 문장 수준으로 구체적)"},
                     "cite_uids": {"type": "array", "items": {"type": "string"}}},
                     "required": ["axis", "what_they_look_for", "evidence_bar", "cite_uids"]}},
        "red_flags": {"type": "array", "items": {"type": "object", "properties": {
            "flag": {"type": "string"}, "cite_uids": {"type": "array", "items": {"type": "string"}}},
            "required": ["flag", "cite_uids"]}},
        "contrast": {"type": "array", "description": "인접 단계와의 차이. lift 수치를 반드시 포함",
                     "items": {"type": "object", "properties": {
                         "vs": {"type": "string"}, "difference": {"type": "string"}}, "required": ["vs", "difference"]}},
        "interview_style": {"type": "string", "description": "process_pct 수치 기반 전형·면접 방식과 준비 포인트"},
        "question_bank": {"type": "array", "items": {"type": "object", "properties": {
            "q": {"type": "string"}, "follow_up": {"type": "string"}, "from_uid": {"type": "string"}},
            "required": ["q", "follow_up", "from_uid"]}, "description": "work_items_for_questions에서 만든 질문 8~12개"},
        "candidate_advice": {"type": "array", "items": {"type": "string"},
                             "description": "이 단계에 지원하는 백엔드 개발자가 이력서에서 앞세울 것/피할 것 4~6개"},
    },
    "required": ["one_liner", "context", "axes", "red_flags", "contrast", "interview_style", "question_bank", "candidate_advice"],
}

INSTRUCTION = """너는 채용 데이터로 면접관 페르소나를 만드는 분석가다. 입력 JSON(한 단계의 공고 통계·원문 인용)만 근거로 쓴다.
규칙:
- 실존 회사나 인물을 흉내 내지 않는다. "이 단계 회사 면접관의 일반적 관점"이다.
- 모든 axes/red_flags/question_bank 항목은 입력에 실제로 있는 uid를 인용한다. 입력에 없는 사실을 만들지 않는다.
- distinctive_axes(lift>=1.2)를 반드시 axes에 포함하고, weak_axes는 "상대적으로 덜 본다"고 contrast에 쓴다.
- evidence_bar는 이 단계 맥락에 맞게 구체적으로 쓴다(예: 초기=직접 끝까지 만든 범위, 빅테크=지표·용량추정). 2점=행동만, 3점=결과 수치, 4점=수치+측정 방법+본인 역할, 5점=4+의사결정 근거·트레이드오프.
- contrast는 입력의 neighbors lift 수치를 인용해 "이 단계가 무엇을 더/덜 보는지" 쓴다.
- confidence가 low면 one_liner 끝에 "(표본 적음)"을 붙인다.
- 한국어로 간결하게."""


def compact(p: dict, neighbors: dict) -> dict:
    keep = ["band", "postings", "companies", "confidence", "axis_weight", "lift", "distinctive_axes", "weak_axes",
            "process_pct", "min_years_median", "scope", "product_maturity", "hiring_reason", "domains", "role_types",
            "stack_flexibility"]
    c = {k: p[k] for k in keep}
    c["axis_quotes"] = {a: [{"q": q["quote"][:140], "uid": q["uid"]} for q in qs[:5]] for a, qs in p["axis_quotes"].items()}
    c["red_flags"] = [{"flag": f["flag"], "uid": f["uid"]} for f in p["red_flags"][:15]]
    c["team_problems"] = [{"t": t["text"][:160], "uid": t["uid"]} for t in p["team_problems"][:12]]
    c["work_items_for_questions"] = [{"q": w["quote"][:120], "uid": w["uid"]} for w in p["work_items_for_questions"][:30]]
    c["neighbors"] = neighbors
    return c


def valid_uids(p: dict) -> set:
    s = set()
    for qs in list(p["axis_quotes"].values()) + list(p["nice_quotes"].values()):
        s |= {q["uid"] for q in qs}
    s |= {f["uid"] for f in p["red_flags"]} | {t["uid"] for t in p["team_problems"]} | {w["uid"] for w in p["work_items_for_questions"]}
    return s


def write(band: str, model: str):
    p = json.loads((DATA / f"{band}.json").read_text("utf-8"))
    if p["postings"] == 0:
        return None
    idx = ORDER.index(band)
    neighbors = {}
    for nb in ORDER[max(0, idx - 1): idx + 2]:
        if nb != band and (DATA / f"{nb}.json").exists():
            q = json.loads((DATA / f"{nb}.json").read_text("utf-8"))
            neighbors[nb] = {"postings": q["postings"], "lift": q["lift"], "process_pct": q["process_pct"]}
    payload = json.dumps(compact(p, neighbors), ensure_ascii=False)
    proc = subprocess.run([CLAUDE, "-p", INSTRUCTION, "--model", model, "--output-format", "json", "--json-schema",
                           json.dumps(SCHEMA), "--tools", "", "--strict-mcp-config", "--no-session-persistence"],
                          input=payload, capture_output=True, text=True, timeout=600, cwd="/tmp")
    out = json.loads(proc.stdout)
    card = out["structured_output"]
    ok = valid_uids(p)
    dropped = 0
    for a in card["axes"]:
        a["cite_uids"] = [u for u in a["cite_uids"] if u in ok]
    for f in card["red_flags"]:
        f["cite_uids"] = [u for u in f["cite_uids"] if u in ok]
    before = len(card["red_flags"]) + len(card["question_bank"])
    card["red_flags"] = [f for f in card["red_flags"] if f["cite_uids"]]
    card["question_bank"] = [q for q in card["question_bank"] if q["from_uid"] in ok]
    dropped = before - len(card["red_flags"]) - len(card["question_bank"])
    card["_meta"] = {"cost_usd": out.get("total_cost_usd"), "dropped_uncited": dropped, "model": model}
    (DATA / f"{band}.card.json").write_text(json.dumps(card, ensure_ascii=False, indent=1), "utf-8")
    render(band, p, card)
    return card["_meta"]


def render(band, p, card):
    fmt = lambda axes: ", ".join("%s ×%s" % (a, p["lift"][a]) for a in axes) or "없음"
    dist, weak = fmt(p["distinctive_axes"]), fmt(p["weak_axes"])
    L = [f"# {LABEL[band]} 면접관",
         f"> {card['one_liner']}", "",
         f"- 근거: 공고 **{p['postings']}건 / {p['companies']}개사**, 신뢰도 **{p['confidence']}** (자동 생성 — `crawler/persona_build.py` → `persona_write.py`)",
         f"- 성격: 실존 회사·인물이 아닌 \"이 단계 회사 면접관의 일반적 관점\". 원본 수치: `data/personas/{band}.json`",
         f"- 특징 축(lift≥1.2): {dist}  /  덜 보는 축(≤0.8): {weak}",
         "", "## 맥락  `[통계]`", card["context"], "", "## 평가 축과 이 단계의 증거 기준", ""]
    for a in card["axes"]:
        L += [f"### {a['axis']} — 가중치 {p['axis_weight'][a['axis']]} (lift ×{p['lift'][a['axis']]})",
              a["what_they_look_for"], "",
              "| 점수 | 이 단계에서의 기준 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in a["evidence_bar"].items()] + \
             [f"\n근거 공고: {', '.join(a['cite_uids']) or '(인용 없음)'}", ""]
    L += ["## 경계 신호 (탈락 요인)  `[공고]` 해당 공고 문맥에서 추출", ""] + [f"- {f['flag']} — {', '.join(f['cite_uids'])}" for f in card["red_flags"]]
    L += ["", "## 인접 단계와의 차이  `[통계]` lift 수치 기반 / 해석은 `[단계추정]`", ""] + [f"- vs **{c['vs']}**: {c['difference']}" for c in card["contrast"]]
    L += ["", "## 전형·면접 방식", card["interview_style"], "", "## 질문 은행 (실제 업무에서 생성)", ""]
    L += [f"- {q['q']}\n  - 꼬리: {q['follow_up']} ({q['from_uid']})" for q in card["question_bank"]]
    L += ["", "## 지원자에게  `[단계추정]` 데이터 기반 가설 — 개별 공고(`/job-fit`)로 반드시 확인", ""] + [f"- {x}" for x in card["candidate_advice"]]
    L += ["", "## 동작 규칙",
          "- `personas/_rubric.md`(점수 앵커·지적 4요소·아첨 방지)를 먼저 따르고, 위 **이 단계의 증거 기준**으로 앵커를 구체화한다.",
          f"- 가중치 `data/personas/{band}.json`의 axis_weight로 총점을 계산한다. 공고 원문 인용은 axis_quotes에서 그대로 가져온다.",
          "- 출력: 축별 점수(0~5, 기준 한 줄) → 지적 목록(4요소) → 약점 3개+ → 가장 큰 레버 1개."]
    (OUT / f"stage-{band}.md").write_text("\n".join(L) + "\n", "utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bands", default=",".join(ORDER))
    ap.add_argument("--model", default="sonnet")
    a = ap.parse_args()
    for b in a.bands.split(","):
        print(b, write(b, a.model))
