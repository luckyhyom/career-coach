"""Render the final feedback deliverable (fixed format, deterministic) from a review result + pack + target fit.

Sections (always in this order so reports are comparable over time and across candidates):
  0 메타        누구·언제·어떤 데이터/모델 기준인지, 품질 지표
  1 한눈에 보기  핵심 3줄 + 가중 총점 + 가장 큰 레버
  2 단계 적합도  (자동 단계 선택 시) 단계별 점수·신뢰도·핵심 갭
  3 축별 평가    가중치 × 점수, 이 단계 기준
  4 우선 개선 3  왜(근거) / 어떻게
  5 라인별 수정안 원문 → 수정안, 근거 출처 유형
  6 공고 매칭    (공고 지정 시) 필수 요건 충족 / 진짜 갭 vs 무시 가능
  7 예상 질문    꼬리질문 포함
  8 한계         추정·의견 비율, 표본 신뢰도, 검증에서 제외된 지적
"""
from __future__ import annotations

import json

LEVEL = {"met": "✅ 충족", "partial": "◐ 부분", "missing": "❌ 미충족"}


def weighted_total(result: dict, pack: dict):
    w = pack["persona"]["axis_weight"]
    scores = {s["axis"]: s["score"] for s in result.get("axis_scores", [])}
    used = {a: w[a] for a in scores if a in w}
    tot = sum(used.values()) or 1
    return round(100 * sum(used[a] * scores[a] / 5 for a in used) / tot, 1)


def render(result: dict, validation: dict, pack: dict, meta: dict, fit: list = None) -> str:
    P = pack["persona"]
    failed = {c["i"] for c in validation["checks"] if c["fails"]}
    issues = [it for i, it in enumerate(result.get("issues", [])) if i not in failed]
    total = weighted_total(result, pack)
    mix = validation["source_mix"]
    L = ["# 이력서 피드백 리포트", "",
         "| 항목 | 값 |", "|---|---|",
         f"| 대상 | {meta.get('candidate', '익명')} |",
         f"| 생성 | {meta.get('created')} · 모델 `{meta.get('model')}` · 비용 ${meta.get('cost_usd') or 0:.4f} |",
         f"| 기준 | 단계 **{P['band']}** ({P.get('confidence')}, 근거 {P.get('postings')}건) · 직무 {pack['request'].get('role') or '-'}"
         + (f" · 공고 `{pack['job']['uid']}` {pack['job']['company']} / {pack['job']['title']}" if pack.get("job") else "") + " |",
         f"| 데이터 | 현재 모집 중 공고 기준 (최근 신규 동향 아님) |",
         f"| 품질 | 검증 통과율 {validation['pass_rate']:.0%} · 날조 의심 {validation['hallucination_rate']:.0%} · 제외된 지적 {len(failed)}개 |",
         f"| 근거 출처 | 공고 {mix.get('공고',0)} · 통계 {mix.get('통계',0)} · 멘토 {mix.get('멘토',0)} · 단계추정 {mix.get('단계추정',0)} · 의견 {mix.get('의견',0)} |",
         "", "## 1. 한눈에 보기", ""]
    L += [f"- {x}" for x in result.get("summary", [])]
    L += [f"- **가중 총점 {total}/100** (이 단계 가중치 기준) · **가장 큰 레버**: {result.get('biggest_lever','')}", ""]
    if fit:
        L += ["## 2. 단계 적합도", "", "| 단계 | 적합도 | 신뢰도(근거 회사) | 연차 감점 | 핵심 갭 |", "|---|---:|---|---:|---|"]
        L += [f"| {f['band']} | {f['fit']} | {f['confidence']} ({f['companies']}개사) | {f['seniority_penalty']} | {', '.join(f['top_gaps'])} |" for f in fit]
        L += ["", "> 적합도 = 단계별 축 가중치 × 이력서 근거 수준(0~3). 근거 회사가 적은 단계는 참고만.", ""]
    L += ["## 3. 축별 평가", "", "| 축 | 가중치 | 점수(0~5) | 이유 |", "|---|---:|---:|---|"]
    for sc in sorted(result.get("axis_scores", []), key=lambda s: -P["axis_weight"].get(s["axis"], 0)):
        L.append(f"| {sc['axis']} | {P['axis_weight'].get(sc['axis'], 0)} | {sc['score']} | {sc['reason']} |")
    L += ["", "## 4. 우선 개선 3가지", ""]
    for i, lv in enumerate(result.get("levers", [])[:3], 1):
        L += [f"**{i}. {lv['title']}** (`{lv['axis']}`)", f"- 왜: {lv['why']}", f"- 어떻게: {lv['how']}", ""]
    L += ["## 5. 라인별 수정안", "", "| # | 심각도 | 원문 | 문제 | 수정안 | 근거 |", "|---|---|---|---|---|---|"]
    for i, it in enumerate(issues, 1):
        cell = lambda t: (t or "").replace("|", "／").replace("\n", " ")
        L.append(f"| {i} | {it['severity']} | {cell(it['resume_quote'])} | {cell(it['problem'])} | {cell(it['fix'])} | "
                 f"[{it['evidence_type']}] {cell(it['evidence'])} |")
    if result.get("job_match"):
        L += ["", "## 6. 공고 매칭 (필수 요건)", "", "| 요건 | 판정 | 이력서 근거 | 갭 |", "|---|---|---|---|"]
        for m in result["job_match"]:
            gap = {"real_gap": "**진짜 갭**", "ignorable": "무시 가능", "none": "-"}[m["gap_type"]]
            L.append(f"| {m['requirement_quote']} | {LEVEL[m['status']]} | {m['resume_evidence']} | {gap} |")
    L += ["", "## 7. 예상 면접 질문", ""]
    L += [f"- {q['q']}\n  - 꼬리: {q['follow_up']}  _(근거: {q['based_on']})_" for q in result.get("interview_questions", [])]
    est = mix.get("단계추정", 0) + mix.get("의견", 0)
    L += ["", "## 8. 이 리포트의 한계", "",
          f"- 단계추정·의견 근거 {est}개는 가설입니다. `[공고]`·`[통계]` 근거를 우선 반영하세요.",
          f"- 단계 데이터 신뢰도: {P.get('confidence')} (근거 {P.get('postings')}건). 회사 균형 가중 적용.",
          f"- 자동 검증(인용 실재·수치 날조·과장 표현)에서 {len(failed)}개 지적을 제외했습니다.",
          "- 정확도 지표는 예비 단계입니다(멘토 라벨 검증 전). `data/eval/README.md` 참고."]
    return "\n".join(L) + "\n"


def to_json(result, validation, pack, meta, fit=None) -> str:
    return json.dumps({"meta": meta, "fit": fit, "weighted_total": weighted_total(result, pack), "result": result,
                       "validation": validation, "request": pack["request"]}, ensure_ascii=False, indent=1)
