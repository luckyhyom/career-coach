"""PII redaction before sending a resume to any external LLM API.

Replaces emails, phone numbers, resident registration numbers, street addresses (best effort),
personal URLs and configured names. Names come from env REDACT_NAMES (comma separated) because
Korean names cannot be detected reliably by regex.
"""
from __future__ import annotations

import os
import re

PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"\b01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b0\d{1,2}[-.\s]\d{3,4}[-.\s]\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b"), "[RRN]"),
    (re.compile(r"(?:서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충[북남]|전[북남]|경[북남]|제주)\S*\s+\S+[시군구]\s+\S+(?:로|길|동)\s*\d[\d-]*"), "[ADDRESS]"),
    (re.compile(r"https?://(?:www\.)?(?:linkedin\.com/in|instagram\.com|facebook\.com)/\S+"), "[PROFILE_URL]"),
]


def redact(text: str, extra_names=None) -> tuple:
    """Return (redacted_text, counts)."""
    counts = {}
    for pat, tag in PATTERNS:
        text, n = pat.subn(tag, text)
        if n:
            counts[tag] = counts.get(tag, 0) + n
    names = [n.strip() for n in (os.environ.get("REDACT_NAMES", "").split(",") + list(extra_names or [])) if n.strip()]
    for name in names:
        text, n = re.subn(re.escape(name), "[NAME]", text)
        if n:
            counts["[NAME]"] = counts.get("[NAME]", 0) + n
    return text, counts
