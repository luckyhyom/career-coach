"""Rule-based extraction (no LLM): skills, years of experience, coding test / assignment flags."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from . import db

HERE = Path(__file__).resolve().parent


def load_skill_patterns() -> Dict[str, Tuple[str, List[re.Pattern]]]:
    raw = yaml.safe_load((HERE / "skills_dict.yaml").read_text("utf-8"))
    out = {}
    for group, skills in raw.items():
        for name, pats in skills.items():
            out[name] = (group, [re.compile(p, re.I) for p in pats])
    return out


YEARS_RANGE = re.compile(r"(\d{1,2})\s*(?:년|years?)\s*(?:이상)?\s*[~\-–]\s*(\d{1,2})\s*(?:년|years?)")
YEARS_MIN = re.compile(r"(?:경력\s*)?(\d{1,2})\s*(?:년|years?)\s*(?:이상|\+|or more|차?\s*이상)")
NEWBIE = re.compile(r"신입|경력\s*무관|junior|주니어|entry", re.I)
CODING_TEST = re.compile(r"코딩\s*테스트|코테|알고리즘\s*(?:테스트|시험)|라이브\s*코딩|coding\s*test|online\s*judge|프로그래머스\s*테스트", re.I)
ASSIGNMENT = re.compile(r"과제\s*(?:전형|테스트)?|사전\s*과제|take[\s-]*home|assignment", re.I)


def parse_years(text: str) -> Tuple[Optional[int], Optional[int]]:
    m = YEARS_RANGE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    mins = [int(x) for x in YEARS_MIN.findall(text) if int(x) <= 20]
    if mins:
        return min(mins), None
    if NEWBIE.search(text):
        return 0, None
    return None, None


def extract_row(row, patterns) -> dict:
    body = "\n".join(filter(None, [row["title"], row["description"], row["qualifications"], row["preferred"]]))
    source_skills = " ".join(json.loads(row["source_skills"] or "[]"))
    hay = body + "\n" + source_skills
    skills = sorted(name for name, (_, pats) in patterns.items() if any(p.search(hay) for p in pats))
    exp_text = " ".join(filter(None, [row["experience"], row["title"], row["qualifications"]]))
    lo, hi = parse_years(exp_text)
    steps = " ".join(json.loads(row["steps"] or "[]"))
    return {
        "skills": json.dumps(skills, ensure_ascii=False),
        "min_years": lo, "max_years": hi,
        "coding_test": int(bool(CODING_TEST.search(body + " " + steps))),
        "assignment": int(bool(ASSIGNMENT.search(body + " " + steps))),
        "is_backend": 1,
    }


def run(force: bool = False) -> int:
    con = db.connect()
    patterns = load_skill_patterns()
    q = "SELECT * FROM jobs" + ("" if force else " WHERE extracted_at IS NULL")
    n = 0
    for row in con.execute(q).fetchall():
        e = extract_row(row, patterns)
        con.execute(
            "UPDATE jobs SET skills=?, min_years=?, max_years=?, coding_test=?, assignment=?, is_backend=?, extracted_at=? WHERE uid=?",
            (e["skills"], e["min_years"], e["max_years"], e["coding_test"], e["assignment"], e["is_backend"], db.now(), row["uid"]),
        )
        n += 1
    con.commit()
    return n
