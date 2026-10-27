"""Recruiter panel: each stage persona judges the resume independently (no averaging), then deterministic aggregation.

Adopted from the "Recruiter Review v1" design:
  - verdict per persona (PASS / HOLD / REJECT), never averaged
  - exactly ONE kill_reason per persona + first-10-seconds impression + ONE before→after fix
  - market fit in SEATS = number of real open postings each persona represents (stack-position split)
  - consensus kill points: grouped by axis, counted by INDEPENDENT votes (personas with near-identical
    weight vectors count once), sorted by votes then seats
  - noise rule: a point raised by ≤1 independent vote whose axis is not low for most personas → "대응하지 마세요"
  - promotion rule: an axis scored ≤2 by at least half the personas is promoted even without kill votes
  - regression: a `before` sentence chosen again in the next run means the previous fix did not work
"""
from __future__ import annotations

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from crawler.insight import AXES
from .llm import complete
from .redact import redact

ROOT = Path(__file__).resolve().parent.parent
PDIR = ROOT / "data" / "personas"
BANDS = ["early", "growth", "late", "bigtech", "mid"]
LABEL = {"early": "초기(시드~A)", "growth": "성장기(B~C)", "late": "후기·유니콘", "bigtech": "대기업·빅테크", "mid": "중견·상장·SI"}
VERDICTS = ["PASS", "HOLD", "REJECT"]
SIM_SAME = 0.8  # personas whose weight DEVIATIONS (from the panel mean) are this similar count as one vote
# raw weight vectors all score ~0.95+ because shared axes dominate; centering removes that common part


def schema(axes):
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": VERDICTS},
            "scores": {"type": "object", "properties": {a: {"type": "integer", "minimum": 0, "maximum": 5} for a in axes},
                       "required": list(axes)},
            "kill_reason": {"type": "string", "description": "서류 판정을 가른 결정적 이유 정확히 1개 (이력서 사실 기반)"},
            "kill_axis": {"type": "string", "enum": list(AXES)},
            "kill_quote": {"type": "string", "description": "kill_reason의 근거가 되는 이력서 원문 그대로. 부재를 지적하면 빈 문자열"},
            "first_10s": {"type": "string", "description": "첫 10초 훑어보기에서 눈에 걸린 것 2~4문장"},
            "one_fix": {"type": "object", "properties": {
                "before": {"type": "string", "description": "이력서 원문 한 문장 그대로"},
                "after": {"type": "string", "description": "고친 문장. 이력서에 없는 수치·경험 금지, 모르는 값은 [측정값]"}},
                "required": ["before", "after"]},
            "interview_q": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
                "q": {"type": "string"}, "topic": {"type": "string", "description": "질문 주제 8자 이내 (예: 자동할당, 정합성, 이직궤적)"}},
                "required": ["q", "topic"]}},
        },
        "required": ["verdict", "scores", "kill_reason", "kill_axis", "kill_quote", "first_10s", "one_fix", "interview_q"],
    }


def system_prompt(band, prof, card):
    top = sorted(prof["axis_weight"], key=lambda a: -prof["axis_weight"][a])[:5]
    bars = {a["axis"]: a["evidence_bar"] for a in (card or {}).get("axes", []) if a["axis"] in top}
    flags = [f["flag"] for f in (card or {}).get("red_flags", [])][:5]
    return f"""너는 "{LABEL[band]}" 단계 회사의 서류 검토자다(실존 회사·인물 아님). 근거: 현재 모집 중 공고 {prof['postings']}건/{prof['companies']}개사.
규칙:
- 지원자의 연차·스택·경력은 **이력서에서만** 읽는다. 전제나 추측을 채우지 않는다.
- 이 단계가 중시하는 축과 가중치: {json.dumps({a: prof['axis_weight'][a] for a in top}, ensure_ascii=False)}
- 점수 기준(이 단계): {json.dumps(bars, ensure_ascii=False) if bars else "0 없음/1 키워드/2 행동/3 결과수치/4 수치+방법+역할/5 4+의사결정 근거"}
- 이 단계의 경계 신호: {json.dumps(flags, ensure_ascii=False)}
- 이 단계 전형 비율(%): {json.dumps(prof.get('process_pct', {}), ensure_ascii=False)}
- verdict: PASS=이 단계 서류 통과 가능 / HOLD=다른 지원자와 비교 보류 / REJECT=탈락.
- kill_reason은 판정을 가른 이유 **딱 하나**. 일반론 금지, 이력서 사실을 근거로.
- one_fix.before는 이력서 문장 그대로 복사, after는 그 문장을 고친 것. 모르는 수치는 [측정값].
- interview_q 3개는 이 이력서에서 실제로 물을 질문.
- 한국어. JSON만."""


def _n(s):
    return re.sub(r"^[-*·•]+|\s+", "", (s or "").strip()).lower()


def _in_resume(q, nres):
    parts = [p for p in re.split(r"\s+/\s+|\n|…|\.\.\.", q or "") if p.strip(" #-•")]
    return bool(parts) and all(_n(p.strip(" #-•"))[:50] in nres for p in parts)


def check(out, resume):
    nres = _n(resume)
    problems = []
    if out["kill_quote"] and not _in_resume(out["kill_quote"], nres):
        problems.append("kill_quote_not_in_resume")
    if not _in_resume(out["one_fix"]["before"], nres):
        problems.append("before_not_in_resume")
    if not out["one_fix"]["after"].strip():
        problems.append("after_empty")
    num = re.compile(r"(?<![A-Za-z0-9.,])(\d[\d,]*(?:\.\d+)?)\s*(%|ms|초|분|시간|건|배|만|억|개|명|회|x|TPS|rps|GB|MB)")
    have = {m.group(1).replace(",", "") for m in num.finditer(resume)}
    new = {m.group(1).replace(",", "") for m in num.finditer(out["one_fix"]["after"].replace("[측정값]", ""))} - have
    if new:
        problems.append(f"after_invented_numbers:{sorted(new)[:3]}")
    return problems


def judge(band, resume, model):
    prof = json.loads((PDIR / f"{band}.json").read_text("utf-8"))
    cardp = PDIR / f"{band}.card.json"
    card = json.loads(cardp.read_text("utf-8")) if cardp.exists() else None
    top = sorted(prof["axis_weight"], key=lambda a: -prof["axis_weight"][a])[:5]
    sysmsg = system_prompt(band, prof, card)
    for attempt in range(2):  # return-value check; one retry with the problems listed
        res = complete(model, sysmsg + ("" if attempt == 0 else f"\n이전 응답 문제: {problems}. 이력서 원문을 정확히 복사하라."),
                       resume, schema(top))
        out = res["json"]
        problems = check(out, resume) if out else ["no_json"]
        if not problems:
            break
    return {"band": band, "label": LABEL[band], "result": out, "problems": problems, "attempts": attempt + 1,
            "weights": {a: prof["axis_weight"][a] for a in top}, "seats": prof["postings"], "companies": prof["companies"],
            "confidence": prof["confidence"], "stack_position": prof.get("stack_position", {}),
            "vec": prof["axis_weight"], "cost_usd": res["cost_usd"], "model": res["model"]}


def _cos(a, b):
    num = sum(a[k] * b[k] for k in a)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0


def aggregate(panel, previous=None):
    ok = [p for p in panel if p["result"]]
    # independence groups (union-find on cosine similarity of persona weight vectors)
    parent = {p["band"]: p["band"] for p in ok}
    find = lambda x: x if parent[x] == x else find(parent[x])
    keys = set().union(*(p["vec"] for p in ok)) if ok else set()
    mean = {k: sum(p["vec"].get(k, 0) for p in ok) / len(ok) for k in keys}
    dev = {p["band"]: {k: p["vec"].get(k, 0) - mean[k] for k in keys} for p in ok}
    for i, a in enumerate(ok):
        for b in ok[i + 1:]:
            if _cos(dev[a["band"]], dev[b["band"]]) > SIM_SAME:
                parent[find(b["band"])] = find(a["band"])
    seats = {v: sum(p["seats"] for p in ok if p["result"]["verdict"] == v) for v in VERDICTS}
    stack_seats = {}
    for p in ok:
        for k, n in p["stack_position"].items():
            stack_seats.setdefault(k, {v: 0 for v in VERDICTS})[p["result"]["verdict"]] += n
    # consensus by kill_axis
    by_axis = {}
    for p in ok:
        by_axis.setdefault(p["result"]["kill_axis"], []).append(p)
    low = {a: [p["band"] for p in ok if p["result"]["scores"].get(a, 5) <= 2] for a in
           set(AXES) | set(by_axis) | {k for p in ok for k in p["result"]["scores"]}}
    half = max(1, math.ceil(len(ok) / 2))
    points = []
    for axis, ps in by_axis.items():
        votes = len({find(p["band"]) for p in ps})
        rep_seats = sum(p["seats"] for p in ps)
        promoted = len(low[axis]) >= half
        points.append({"axis": axis, "votes": votes, "raised_by": [p["band"] for p in ps], "seats": rep_seats,
                       "reasons": [{"band": p["band"], "text": p["result"]["kill_reason"], "quote": p["result"]["kill_quote"]} for p in ps],
                       "act": votes >= 2 or promoted, "low_in": low[axis]})
    for axis, bands in low.items():  # promotion: low for most personas but nobody's kill reason
        if len(bands) >= half and axis not in by_axis:
            points.append({"axis": axis, "votes": 0, "raised_by": [], "seats": sum(p["seats"] for p in ok if p["band"] in bands),
                           "reasons": [], "act": True, "low_in": bands, "promoted": True})
    points.sort(key=lambda x: (-x["votes"], -x["seats"]))
    # same line picked as one_fix by independent personas = strongest, most concrete consensus
    fixes = {}
    for p in ok:
        fixes.setdefault(_n(p["result"]["one_fix"]["before"]), []).append(p)
    fix_consensus = sorted(({"before": ps[0]["result"]["one_fix"]["before"], "bands": [p["band"] for p in ps],
                             "votes": len({find(p["band"]) for p in ps}), "afters": [p["result"]["one_fix"]["after"] for p in ps]}
                            for ps in fixes.values()), key=lambda x: -x["votes"])
    # interview topics
    topics = {}
    for p in ok:
        for q in p["result"]["interview_q"]:
            topics.setdefault(_n(q["topic"])[:8], {"topic": q["topic"], "items": []})["items"].append({"band": p["band"], "q": q["q"]})
    topic_list = sorted(topics.values(), key=lambda t: -len({i["band"] for i in t["items"]}))
    # regression: same `before` chosen again
    prev_before = {_n(p["result"]["one_fix"]["before"]) for p in (previous or []) if p.get("result")}
    repeats = [p["band"] for p in ok if _n(p["result"]["one_fix"]["before"]) in prev_before]
    groups = {}
    for p in ok:
        groups.setdefault(find(p["band"]), []).append(p["band"])
    return {"seats": seats, "stack_seats": stack_seats, "points": points, "topics": topic_list,
            "fix_consensus": fix_consensus,
            "repeats_from_previous": repeats, "independence_groups": list(groups.values())}


def render(panel, agg, meta):
    ok = [p for p in panel if p["result"]]
    L = [f"# 채용담당자 패널 리뷰", "",
         f"- 대상: {meta['candidate']} · 생성 {meta['created']} · 모델 `{meta['model']}` · 비용 ${meta['cost']:.4f}",
         f"- 페르소나 {len(ok)}명 **독립 판정 · 평균 없음** · 근거: 현재 모집 중 공고(단계별, 수집일 {meta.get('data_as_of') or '알 수 없음'}) · 연차·스택은 이력서에서만 읽음",
         f"- 반환값 검사 재시도: {sum(p['attempts'] - 1 for p in panel)}회 · 남은 문제: {[(p['band'], p['problems']) for p in panel if p['problems']] or '없음'}",
         "", "## ① 판정 보드", ""]
    for v in VERDICTS:
        L.append(f"- **{v} {sum(1 for p in ok if p['result']['verdict'] == v)}**: {', '.join(p['label'] for p in ok if p['result']['verdict'] == v) or '—'}")
    axes = sorted({a for p in ok for a in p["weights"]})
    L += ["", "| 페르소나 | 판정 | " + " | ".join(axes) + " |", "|---|---|" + "---|" * len(axes)]
    for p in ok:
        cells = [f"{p['result']['scores'][a]} w{int(round(p['weights'][a] * 100))}" if a in p["weights"] else "·" for a in axes]
        L.append(f"| {p['label']} ({p['companies']}개사, {p['confidence']}) | {p['result']['verdict']} | " + " | ".join(cells) + " |")
    L += ["", "> 셀 = 점수(0~5)와 그 페르소나의 축 가중치(w, %). 열을 세로로 훑어 축이 페르소나마다 갈리는지 보세요.",
          "", "## ② 시장 적합도 (자리 = 그 페르소나가 대표하는 현재 모집 중 공고 수)", ""]
    L += [f"- **{v} {agg['seats'][v]}자리**" for v in VERDICTS]
    L += ["", "| 스택 위치 (Node/TS) | PASS | HOLD | REJECT |", "|---|---:|---:|---:|"]
    name = {"target_required": "필수", "target_preferred": "우대", "other_required": "다른 스택 필수", "agnostic": "스택 무관"}
    for k, d in agg["stack_seats"].items():
        L.append(f"| {name.get(k, k)} | {d['PASS']} | {d['HOLD']} | {d['REJECT']} |")
    L += ["", "## ③ 합의된 킬 포인트 (수정 우선순위)", "",
          f"> 독립 표 = 가중치가 비슷한(코사인>{SIM_SAME}) 페르소나는 1표로 셈. 묶음: {agg['independence_groups']}", ""]
    for i, pt in enumerate(agg["points"], 1):
        tag = "" if pt["act"] else " — **대응하지 마세요** (독립 표 1 이하이고 이 축을 낮게 본 페르소나가 절반 미만)"
        if pt.get("promoted"):
            tag = " — **승격** (킬 포인트로 지목되진 않았지만 절반 이상이 2점 이하)"
        L.append(f"**{i}. `{pt['axis']}`** · 독립 표 {pt['votes']} · 대표 자리 {pt['seats']} · 낮게 본 페르소나 {pt['low_in']}{tag}")
        for r in pt["reasons"]:
            L.append(f"- {LABEL[r['band']]}: {r['text']}" + (f"  \n  근거: “{r['quote']}”" if r["quote"] else ""))
        L.append("")
    L += ["## ④ 면접 예상 질문 (여러 페르소나가 겹쳐 물은 주제가 위)", ""]
    for t in agg["topics"]:
        bands = sorted({i["band"] for i in t["items"]})
        L.append(f"**{t['topic']}** ({len(bands)}명: {', '.join(LABEL[b] for b in bands)})")
        L += [f"- {LABEL[i['band']]}: {i['q']}" for i in t["items"]]
        L.append("")
    L += ["## ⑤ 고칠 것 (before는 이력서 원문, after는 페르소나 제안)", ""]
    if agg["repeats_from_previous"]:
        L.append(f"> ⚠️ 이전 판과 같은 문장을 다시 지목: {agg['repeats_from_previous']} — 지난 수정이 먹히지 않았습니다.\n")
    lab = {p["band"]: p["label"] for p in ok}
    for i, fx in enumerate(agg.get("fix_consensus", []), 1):
        tag = " — **합의**" if fx["votes"] >= 2 else ""
        L += [f"**{i}. 독립 표 {fx['votes']}** ({', '.join(lab[b] for b in fx['bands'])}){tag}", f"- before: {fx['before']}"]
        L += [f"- after ({lab[b]}): {a}" for b, a in zip(fx["bands"], fx["afters"])] + [""]
    L += ["## ⑥ 첫 10초 인상", ""] + [f"- **{p['label']}**: {p['result']['first_10s']}" for p in ok]
    thin = [f"{p['label']} N={p['seats']}" for p in ok if p["seats"] <= 12]
    L += ["", "## 감안할 것", "",
          f"- 표본이 얇은 페르소나: {thin or '없음'} — 공고 1건이 {round(100 / min([p['seats'] for p in ok] or [1]))}%p까지 움직입니다.",
          "- 판정은 '현재 모집 중' 공고 기준이며 최근 신규 채용 동향이 아닙니다.",
          "- 페르소나는 데이터 기반 일반 관점이고, 실제 회사·면접관의 판단과 다를 수 있습니다."]
    return "\n".join(L) + "\n"


def run(resume_text, candidate="익명", model="route:review", previous=None):
    text, _ = redact(resume_text)
    bands = [b for b in BANDS if (PDIR / f"{b}.json").exists() and json.loads((PDIR / f"{b}.json").read_text("utf-8"))["companies"] >= 3]
    if not bands:
        raise SystemExit("No persona data yet (data/personas/). A fresh clone ships without posting data — "
        "build it first: AGENTS.md section 0 / docs/OPERATIONS.md '데이터 갱신'")
    with ThreadPoolExecutor(max_workers=len(bands)) as ex:
        panel = list(ex.map(lambda b: judge(b, text, model), bands))
    agg = aggregate(panel, previous)
    meta = {"candidate": candidate, "created": time.strftime("%Y-%m-%d %H:%M"), "model": panel[0]["model"] if panel else model,
            "cost": sum(p["cost_usd"] or 0 for p in panel)}
    return panel, agg, meta
