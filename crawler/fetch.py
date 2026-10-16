"""Polite HTTP fetcher.

- One request at a time per domain, token-bucket rate limit + random jitter
- robots.txt checked before every URL (cached per domain)
- 429/503 -> exponential backoff honoring Retry-After; site aborted after repeated failures
- Per-site request budget per run
- Conditional GET (ETag / Last-Modified) with an on-disk cache
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import random
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

log = logging.getLogger("fetch")

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


class SiteAborted(Exception):
    """Raised when a site keeps failing or the request budget is used up."""


class Fetcher:
    def __init__(
        self,
        user_agent: str,
        rate_per_sec: float = 0.3,
        jitter: tuple = (0.5, 1.5),
        max_requests: int = 1500,
        max_failures: int = 3,
        timeout: int = 25,
    ):
        self.user_agent = user_agent
        self.min_interval = 1.0 / rate_per_sec
        self.jitter = jitter
        self.max_requests = max_requests
        self.max_failures = max_failures
        self.timeout = timeout
        self.requests_made = 0
        self.cache_hits = 0
        self._last_request: Dict[str, float] = {}
        self._robots: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._failures = 0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- rate limiting ----------
    def _wait_turn(self, domain: str) -> None:
        last = self._last_request.get(domain)
        if last is not None:
            gap = self.min_interval + random.uniform(*self.jitter)
            sleep_for = last + gap - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._last_request[domain] = time.monotonic()

    # ---------- robots ----------
    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        base = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._wait_turn(parts.netloc)
                self.requests_made += 1
                req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    rp.parse(resp.read().decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                # 4xx on robots.txt means "no restrictions"; 5xx means be conservative.
                rp.parse([] if 400 <= e.code < 500 else ["User-agent: *", "Disallow: /"])
            except Exception as e:  # network error -> be conservative
                log.warning("robots.txt unavailable for %s (%s); treating as disallowed", base, e)
                rp.parse(["User-agent: *", "Disallow: /"])
            self._robots[base] = rp
        return rp.can_fetch(self.user_agent, url)

    # ---------- cache ----------
    @staticmethod
    def _cache_paths(url: str):
        h = hashlib.sha1(url.encode()).hexdigest()
        return CACHE_DIR / f"{h}.body.gz", CACHE_DIR / f"{h}.meta.json"

    @staticmethod
    def _read(body_p) -> Optional[str]:
        """Raw page snapshot (gzip). Falls back to legacy uncompressed .body files."""
        if body_p.exists():
            return gzip.decompress(body_p.read_bytes()).decode("utf-8")
        legacy = body_p.with_suffix("")  # .body
        return legacy.read_text("utf-8") if legacy.exists() else None

    @staticmethod
    def _write(body_p, text: str) -> None:
        body_p.write_bytes(gzip.compress(text.encode("utf-8"), compresslevel=6))
        legacy = body_p.with_suffix("")
        if legacy.exists():
            legacy.unlink()

    def cached(self, url: str) -> Optional[str]:
        body, _ = self._cache_paths(url)
        return self._read(body)

    # ---------- main ----------
    def get(self, url: str, use_cache: bool = True, revalidate: bool = True) -> Optional[str]:
        """Return body text, or None if disallowed / not found.

        use_cache + not revalidate: return cached body without any request (detail pages).
        use_cache + revalidate: conditional GET (listing pages, sitemaps).
        """
        body_p, meta_p = self._cache_paths(url)
        if use_cache and not revalidate:
            cached = self._read(body_p)
            if cached is not None:
                self.cache_hits += 1
                return cached

        if not self.allowed(url):
            log.info("robots.txt disallows %s", url)
            return None
        if self.requests_made >= self.max_requests:
            raise SiteAborted(f"request budget ({self.max_requests}) used up")

        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip", "Accept-Language": "ko-KR,ko;q=0.9"}
        if use_cache and meta_p.exists():
            meta = json.loads(meta_p.read_text())
            if meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                headers["If-Modified-Since"] = meta["last_modified"]

        domain = urlparse(url).netloc
        backoff = 10.0
        for attempt in range(5):
            self._wait_turn(domain)
            self.requests_made += 1
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    text = raw.decode(resp.headers.get_content_charset() or "utf-8", "replace")
                    self._write(body_p, text)
                    meta_p.write_text(json.dumps({
                        "url": url,
                        "etag": resp.headers.get("ETag"),
                        "last_modified": resp.headers.get("Last-Modified"),
                        "fetched_at": time.time(),
                    }))
                    self._failures = 0
                    return text
            except urllib.error.HTTPError as e:
                if e.code == 304 and self._read(body_p) is not None:
                    self.cache_hits += 1
                    return self._read(body_p)
                if e.code in (404, 410):
                    return None
                if e.code in (403,):
                    # Bot protection: do not try to get around it.
                    raise SiteAborted(f"403 Forbidden at {url} (bot protection?)")
                if e.code in (429, 500, 502, 503, 504):
                    retry_after = e.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                    wait = min(wait, 300.0)
                    log.warning("HTTP %s on %s; backing off %.0fs", e.code, url, wait)
                    time.sleep(wait)
                    backoff *= 2
                    continue
                log.warning("HTTP %s on %s", e.code, url)
                return None
            except Exception as e:
                log.warning("error on %s: %s", url, e)
                time.sleep(backoff)
                backoff *= 2
        self._failures += 1
        if self._failures >= self.max_failures:
            raise SiteAborted(f"{self._failures} consecutive failures")
        return None
