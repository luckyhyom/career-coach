"""Resume -> structured candidate profile (axis evidence levels), provider-agnostic, cached by resume hash.

Only the resume is required, so this works for anyone (no personal notes needed).
Every axis level must cite a verbatim resume quote; levels whose quote is not in the resume are reset to 0.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from crawler.insight import AXES
from .llm import complete
from .redact import redact

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "candidates"  # gitignored (derived from personal documents)

SCHEMA = {
    "type": "object",
    "properties": {
        "years_total": {"type": ["number", "null"], "description": "개발 경력 연수 합계(추정 가능하면)"},
        "role_types": {"type": "array", "items": {"type": "string", "enum": [
            "product_backend", "platform_backend", "fullstack", "sdet_quality", "devops_sre", "data_engineering",
            "ai_ml_engineering", "embedded", "other"]}},
        "domains": {"type": "array", "items": {"type": "string"}},
        "stack": {"type": "array", "items": {"type": "string"}},
        "axis_evidence": {"type": "array", "items": {"type": "object", "properties": {
            "axis": {"type": "string", "enum": list(AXES)},
            "level": {"type": "integer", "minimum": 0, "maximum": 3,
                      "description": "0 근거 없음 / 1 키워드·참여 / 2 구체적 행동 / 3 결과 수치·의사결정 근거까지"},
            "quote": {"type": "string", "description": "이력서 원문 그대로(근거 문장)"}},
            "required": ["axis", "level", "quote"]}},
    },
    "required": ["years_total", "role_types", "domains", "stack", "axis_evidence"],
}
SYSTEM = """이력서를 구조화한다. axis_evidence는 모든 축(""" + ", ".join(AXES) + """)에 대해 하나씩 작성한다.
level 기준: 0 근거 없음 / 1 키워드·참여만 / 2 구체적 행동 / 3 결과 수치나 의사결정 근거까지.
quote는 이력서 원문을 그대로 복사한다(근거 없으면 빈 문자열, level 0). 과대평가하지 않는다. JSON만."""


def _n(s):
    return re.sub(r"\s+", "", s or "").lower()


def parse(resume_text: str, model: str = "route:candidate_parse", use_cache: bool = True) -> dict:
    text, redactions = redact(resume_text)
    key = hashlib.sha1((text + model).encode()).hexdigest()[:16]
    path = CACHE / f"{key}.json"
    if use_cache and path.exists():
        return json.loads(path.read_text("utf-8"))
    out = complete(model, SYSTEM, text, SCHEMA)
    prof = out["json"] or {}
    nt = _n(text)
    dropped = 0
    for a in prof.get("axis_evidence", []):
        if a["level"] > 0 and (not a["quote"] or _n(a["quote"])[:40] not in nt):
            a["level"], a["quote"] = 0, ""  # unsupported claim -> no credit
            dropped += 1
    have = {a["axis"] for a in prof.get("axis_evidence", [])}
    prof.setdefault("axis_evidence", []).extend({"axis": ax, "level": 0, "quote": ""} for ax in AXES if ax not in have)
    prof["_meta"] = {"model": out["model"], "cost_usd": out["cost_usd"], "unsupported_levels_reset": dropped,
                     "redactions": redactions, "resume_hash": key}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prof, ensure_ascii=False, indent=1), "utf-8")
    return prof


def levels(prof: dict) -> dict:
    return {a["axis"]: a["level"] for a in prof["axis_evidence"]}
