"""Deep, structured reading of each posting (once per posting, cached in sqlite).

    .venv/bin/python -m crawler.insight run [--limit N] [--uids u1,u2] [--workers 4]
    .venv/bin/python -m crawler.insight check            # quote validity / coverage report

Uses `claude -p --model haiku` with a JSON schema. Every requirement is stored with a verbatim
quote; quotes that are not found in the posting text are dropped (anti-hallucination gate).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import db
from .extract import BOILERPLATE

log = logging.getLogger("insight")
CLAUDE = str(Path.home() / ".local" / "bin" / "claude")
PROMPT_VERSION = "v1"

AXES = {
    "ownership": "제품 오너십: 문제 정의·가설·실험·지표, 끝까지 책임, 비즈니스 임팩트",
    "scale_performance": "대규모 트래픽·성능·지연시간·확장성",
    "consistency_reliability": "데이터 정합성·트랜잭션·멱등성·장애 대응·고가용성·안정성",
    "code_quality_testing": "코드 품질·테스트·코드리뷰·설계 원칙·리팩터링",
    "infra_ops": "클라우드·컨테이너·CI/CD·모니터링·운영 자동화",
    "integration_legacy": "외부 API/파트너 연동·레거시 개선·마이그레이션·서비스 분리",
    "cs_fundamentals": "CS 기본기·자료구조/알고리즘·OS/네트워크/DB 이론",
    "domain": "특정 도메인 지식(결제·정산·광고·커머스·헬스케어 등)",
    "ai_leverage": "AI/LLM 도구 활용·AI 기능 개발·AI 결과 검증",
    "adaptability": "스택 무관·빠른 학습·영역 확장(풀스택 등)",
    "language_framework": "특정 언어·프레임워크·DB 숙련 (스택 요구)",
    "collaboration": "협업·커뮤니케이션·문서화·리더십·멘토링",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "role_type": {"type": "string", "enum": ["product_backend", "platform_backend", "sdet_quality", "devops_sre",
                                                 "fullstack", "data_engineering", "ai_ml_engineering", "other"]},
        "team_problem": {"type": "string", "description": "이 팀이 풀려는 문제를 1~2문장 한국어로"},
        "product_maturity": {"type": "string", "enum": ["zero_to_one", "scaling", "platformization", "legacy_ops", "unknown"]},
        "hiring_reason": {"type": "string", "enum": ["new_product", "scale", "legacy_replacement", "domain_expansion", "team_growth", "unknown"]},
        "domain": {"type": "string", "description": "결제/정산, 광고, 커머스, 커뮤니티, 헬스케어, B2B SaaS, AI 플랫폼 등 짧게"},
        "stage_hint": {
            "type": "object",
            "properties": {
                "value": {"type": "string", "enum": ["seed", "series_a", "series_b", "series_c_plus", "pre_ipo_unicorn",
                                                     "listed_mid", "enterprise", "big_tech", "foreign", "si_agency", "unknown"]},
                "quote": {"type": "string", "description": "근거 원문(투자 단계·상장·직원 수·MAU 등). 없으면 빈 문자열"},
            },
            "required": ["value", "quote"],
        },
        "items": {
            "type": "array",
            "description": "자격요건(must)·실제 업무(work)·우대(nice) 항목. 공통 채용 안내문은 제외",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["must", "work", "nice"]},
                    "axis": {"type": "string", "enum": list(AXES)},
                    "quote": {"type": "string", "description": "공고 원문 그대로 복사(요약 금지, 120자 이내로 자를 수 있음)"},
                    "gist": {"type": "string", "description": "이 항목이 실제로 원하는 것 한 줄"},
                },
                "required": ["kind", "axis", "quote", "gist"],
            },
        },
        "red_flags": {
            "type": "array",
            "description": "이 팀이 피하려는 지원자 유형(공고 문맥에서 추론). 근거 원문 포함",
            "items": {"type": "object", "properties": {"flag": {"type": "string"}, "quote": {"type": "string"}},
                      "required": ["flag", "quote"]},
        },
        "stack_flexibility": {"type": "string", "enum": ["strict", "flexible", "unknown"]},
        "seniority": {"type": "object", "properties": {
            "min_years": {"type": ["integer", "null"]},
            "scope": {"type": "string", "enum": ["junior", "ic", "senior_ic", "lead", "unknown"]}},
            "required": ["min_years", "scope"]},
        "process": {"type": "object", "properties": {k: {"type": "boolean"} for k in
                    ["assignment", "coding_test", "live_coding", "ai_interview", "culture_fit"]},
                    "required": ["assignment", "coding_test", "live_coding", "ai_interview", "culture_fit"]},
    },
    "required": ["role_type", "team_problem", "product_maturity", "hiring_reason", "domain", "stage_hint",
                 "items", "red_flags", "stack_flexibility", "seniority", "process"],
}

INSTRUCTION = """너는 채용공고 분석가다. 입력된 공고 하나를 스키마에 맞춰 구조화한다.
규칙:
- quote는 반드시 공고 원문에서 그대로 복사한다(띄어쓰기 포함). 요약·번역·의역 금지. 길면 앞부분 120자까지 자른다.
- 회사 소개·복지·법적 고지·전형 안내 문구는 items에 넣지 않는다.
- axis 정의: """ + "; ".join(f"{k}={v}" for k, v in AXES.items()) + """
- 하나의 문장이 여러 축에 걸치면 가장 핵심인 축 하나만 고른다.
- red_flags는 공고가 명시하거나 강하게 시사하는 것만(예: "3개월 경험 쌓기 목적이면 사양", "스택 무관하나 기본기 중시"). 근거 없으면 빈 배열.
- stage_hint는 공고 안에 투자 단계·상장·규모 근거가 있을 때만 값을 넣고, 없으면 unknown과 빈 quote.
"""


MAX_CHARS = 20000
BILINGUAL = re.compile(r"English (?:text )?will follow (?:the )?Korean(?: text)?|English version (?:is )?below|\[English\]", re.I)
EN_START = re.compile(r"\n\s*(?:Company Introduction|About Coupang|Role Overview|Key Responsibilities|What You Will Do)\b", re.I)


def strip_bilingual(desc: str) -> str:
    """Korean+English postings repeat everything; keep the Korean half."""
    if not desc or not BILINGUAL.search(desc):
        return desc
    end = BILINGUAL.search(desc).end()
    after = desc[end:]
    # English section = first English heading that comes after some Korean body text (any length)
    for m in EN_START.finditer(after):
        if re.search(r"[가-힣]", after[:m.start()]):
            return desc[: end + m.start()]
    return desc


def clean_text(row) -> str:
    row = dict(row)
    row["description"] = strip_bilingual(row.get("description") or "")
    parts = [f"[제목] {row['title']}", f"[회사] {row['company']}", f"[경력] {row['experience'] or ''}",
             "[본문]\n" + (row["description"] or ""), "[자격요건]\n" + (row["qualifications"] or ""),
             "[우대사항]\n" + (row["preferred"] or ""), "[전형] " + " / ".join(json.loads(row["steps"] or "[]"))]
    text = "\n".join(parts)
    text = "\n".join(l for l in text.splitlines() if l.strip() and not BOILERPLATE.search(l))
    return text[:MAX_CHARS]



def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def quote_in(q: str, nt: str) -> bool:
    """Whole quote must appear verbatim (whitespace-insensitive). A trailing ellipsis marks allowed truncation."""
    if not q:
        return False
    core = re.sub(r"(…|\.\.\.)\s*$", "", q)
    nq = _norm(core)
    return len(nq) >= 6 and nq in nt


def validate(ins: dict, text: str) -> dict:
    """Drop items/flags whose quote is not verbatim in the text (full quote, not a prefix). Record stats."""
    nt = _norm(text)
    ok = lambda q: quote_in(q, nt)
    items = ins.get("items", [])
    kept = [i for i in items if ok(i.get("quote"))]
    flags = [f for f in ins.get("red_flags", []) if ok(f.get("quote"))]
    sh = ins.get("stage_hint") or {}
    if sh.get("value") not in (None, "unknown") and not ok(sh.get("quote")):
        sh = {"value": "unknown", "quote": "", "dropped": sh.get("value")}
    ins.update(items=kept, red_flags=flags, stage_hint=sh,
               _quality={"items_total": len(items), "items_kept": len(kept),
                         "flags_total": len(ins.get("red_flags", [])), "flags_kept": len(flags)})
    return ins


def analyze(row) -> dict:
    from coach.llm import complete  # provider-agnostic (coach/models.yaml routes.insight_extract)
    text = clean_text(row)
    out = complete("route:insight_extract", INSTRUCTION, text, SCHEMA)
    if not out["json"]:
        raise RuntimeError(f"no structured output from {out['model']}: {str(out['text'])[:200]}")
    ins = validate(out["json"], text)
    ins["_cost_usd"] = out["cost_usd"]
    ins["_model"] = out["model"]
    ins["_input_chars"] = len(text)
    ins["_truncated"] = len(text) >= MAX_CHARS
    return ins


SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS job_insights (
    uid TEXT PRIMARY KEY, version TEXT, data TEXT, created_at TEXT)"""


def run(limit=None, uids=None, workers=4, all_postings=False):
    """Analyze only postings in the shared population (open, Korea, backend, years cap) that lack a current insight."""
    from . import population as P
    con = db.connect()
    con.execute(SCHEMA_SQL)
    done_uids = {u for (u,) in con.execute("SELECT uid FROM job_insights WHERE version=?", (PROMPT_VERSION,))}
    if uids:
        rows = [r for r in con.execute("SELECT * FROM jobs").fetchall() if r["uid"] in set(uids)]
    elif all_postings:
        rows = con.execute("SELECT * FROM jobs").fetchall()
    else:
        rows = P.select(con, "open")
    rows = [r for r in rows if r["uid"] not in done_uids]
    rows = rows[:limit] if limit else rows
    log.info("analyzing %d postings with %d workers", len(rows), workers)
    done = cost = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(analyze, r): r["uid"] for r in rows}
        for f in as_completed(futs):
            uid = futs[f]
            try:
                ins = f.result()
            except Exception as e:  # keep going; retry next run
                log.warning("%s failed: %s", uid, e)
                continue
            con.execute("INSERT OR REPLACE INTO job_insights VALUES (?,?,?,?)",
                        (uid, PROMPT_VERSION, json.dumps(ins, ensure_ascii=False), db.now()))
            con.commit()
            done += 1
            cost += ins.get("_cost_usd") or 0
            if done % 20 == 0:
                log.info("%d/%d done, cost so far $%.3f", done, len(rows), cost)
    log.info("finished %d, cost $%.3f", done, cost)


def revalidate():
    """Re-apply the (stricter) quote check to stored insights without any LLM call."""
    con = db.connect()
    n = dropped = 0
    for uid, data in con.execute("SELECT uid, data FROM job_insights").fetchall():
        row = con.execute("SELECT * FROM jobs WHERE uid=?", (uid,)).fetchone()
        if not row:
            continue
        ins = json.loads(data)
        before = len(ins["items"]) + len(ins["red_flags"])
        cost = ins.get("_cost_usd")
        ins = validate(ins, clean_text(row))
        ins["_cost_usd"] = cost
        dropped += before - len(ins["items"]) - len(ins["red_flags"])
        con.execute("UPDATE job_insights SET data=? WHERE uid=?", (json.dumps(ins, ensure_ascii=False), uid))
        n += 1
    con.commit()
    print(f"revalidated {n} insights, dropped {dropped} items/flags whose full quote is not in the posting")


def check():
    con = db.connect()
    con.execute(SCHEMA_SQL)
    rows = [json.loads(r[0]) for r in con.execute("SELECT data FROM job_insights")]
    it = sum(r["_quality"]["items_total"] for r in rows)
    ik = sum(r["_quality"]["items_kept"] for r in rows)
    ft = sum(r["_quality"]["flags_total"] for r in rows)
    fk = sum(r["_quality"]["flags_kept"] for r in rows)
    from collections import Counter
    rep = {
        "postings": len(rows),
        "quote_valid_rate_items": round(ik / it, 3) if it else None,
        "quote_valid_rate_flags": round(fk / ft, 3) if ft else None,
        "avg_items_kept": round(ik / len(rows), 1) if rows else 0,
        "zero_item_postings": sum(1 for r in rows if not r["items"]),
        "role_type": Counter(r["role_type"] for r in rows).most_common(),
        "stage_hints": Counter(r["stage_hint"]["value"] for r in rows).most_common(),
        "axis_counts": Counter(i["axis"] for r in rows for i in r["items"]).most_common(),
        "cost_usd": round(sum(r.get("_cost_usd") or 0 for r in rows), 3),
    }
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "check", "revalidate"])
    ap.add_argument("--all", action="store_true", help="analyze every posting, not just the shared population")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--uids")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if a.cmd == "run":
        run(a.limit, a.uids.split(",") if a.uids else None, a.workers, a.all)
    elif a.cmd == "revalidate":
        revalidate()
    else:
        check()
