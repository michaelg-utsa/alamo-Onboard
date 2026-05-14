"""
pipeline/fingerprinter.py
--------------------------
Detects whether a URL's content has changed since the last fetch.

Strategy per source (determined by check_headers.py results):
  - CPS PDFs         → ETag       (reliable Azure Blob Storage ETags)
  - CPS HTML page    → content-hash (Last-Modified is dynamic/unreliable)
  - SAWS HTML        → content-hash (no ETag or Last-Modified sent)
  - CoSA HTML        → content-hash (no cache headers)
  - SAPL HTML        → content-hash (no cache headers)

The fingerprint store is a JSON file saved alongside the raw documents.
It tracks both last_fetched (every run) and last_changed (only when
content actually differs) so the UI can show meaningful freshness info.

Usage:
    from sa_utilities.pipeline.fingerprinter import Fingerprinter
    fp = Fingerprinter()
    result = fp.check(url, response)
    if result.changed:
        # re-process content
    fp.save()
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import requests
from sa_utilities.config import RAW_DIR

logger = logging.getLogger(__name__)

FINGERPRINT_FILE = RAW_DIR / "fingerprints.json"

# URLs where Last-Modified is present but known to be dynamic (server stamps
# every response with current time rather than actual content change time).
# For these, we ignore Last-Modified and fall back to content-hash.
UNRELIABLE_LAST_MODIFIED = {
    "www.cpsenergy.com/content/corporate",  # CPS HTML pages via Cloudflare/AEM
}


@dataclass
class FingerprintRecord:
    """Stored state for a single URL."""

    url: str
    fingerprint_method: str  # "etag", "last-modified", or "content-hash"
    fingerprint_value: str  # The actual ETag / date string / hash
    last_fetched: str  # ISO timestamp — updated every run
    last_changed: str  # ISO timestamp — updated only when content changes
    content_bytes: int = 0  # Size of last fetched content


@dataclass
class CheckResult:
    """Returned by Fingerprinter.check() for a single URL."""

    url: str
    changed: bool  # True if content differs from last fetch
    method: str  # Which strategy was used
    fingerprint: str  # The new fingerprint value
    reason: str  # Human-readable explanation (for logging)
    response: requests.Response | None = field(default=None, repr=False)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def _is_unreliable_last_modified(url: str) -> bool:
    return any(pattern in url for pattern in UNRELIABLE_LAST_MODIFIED)


def _choose_strategy(url: str, response: requests.Response) -> str:
    """
    Pick the best fingerprint strategy for this URL/response combination.
    Priority: ETag > Last-Modified (if reliable) > content-hash
    """
    if response.headers.get("ETag"):
        return "etag"
    if response.headers.get("Last-Modified") and not _is_unreliable_last_modified(url):
        return "last-modified"
    return "content-hash"


def _get_fingerprint_value(strategy: str, response: requests.Response) -> str:
    if strategy == "etag":
        return response.headers["ETag"]
    elif strategy == "last-modified":
        return response.headers["Last-Modified"]
    else:
        return _content_hash(response.content)


class Fingerprinter:
    """
    Manages fingerprint records for all tracked URLs.

    Typical usage in an adapter:
        fp = Fingerprinter()
        response = requests.get(url, ...)
        result = fp.check(url, response)
        if result.changed:
            process(response.content)
        fp.save()  # Call once after all URLs are processed
    """

    def __init__(self, store_path: Path = FINGERPRINT_FILE):
        self.store_path = store_path
        self.records: dict[str, FingerprintRecord] = {}
        self._load()

    def _load(self) -> None:
        """Load existing fingerprint records from disk."""
        if not self.store_path.exists():
            logger.debug("No fingerprint store found — starting fresh")
            return
        with open(self.store_path, encoding="utf-8") as f:
            raw = json.load(f)
        for url, data in raw.items():
            self.records[url] = FingerprintRecord(**data)
        logger.debug(f"Loaded {len(self.records)} fingerprint records")

    def save(self) -> None:
        """Persist all fingerprint records to disk."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(
                {url: asdict(rec) for url, rec in self.records.items()},
                f,
                indent=2,
                ensure_ascii=False,
            )
        logger.debug(f"Saved {len(self.records)} fingerprint records → {self.store_path}")

    def check(self, url: str, response: requests.Response) -> CheckResult:
        """
        Compare the response against the stored fingerprint for this URL.

        Updates the in-memory record (call save() to persist).
        Returns a CheckResult indicating whether content has changed.
        """

        if response.status_code != 200:
            logger.warning(
                f"Skipping fingerprint for non-200 response ({response.status_code}): {url}"
            )
            return CheckResult(
                url=url,
                changed=False,
                method="skip",
                fingerprint="",
                reason=f"HTTP {response.status_code} — not recorded",
                response=None,
            )

        now = _now_iso()
        strategy = _choose_strategy(url, response)
        new_value = _get_fingerprint_value(strategy, response)
        content_bytes = len(response.content)
        existing = self.records.get(url)

        if existing is None:
            # First time we've seen this URL
            self.records[url] = FingerprintRecord(
                url=url,
                fingerprint_method=strategy,
                fingerprint_value=new_value,
                last_fetched=now,
                last_changed=now,
                content_bytes=content_bytes,
            )
            return CheckResult(
                url=url,
                changed=True,
                method=strategy,
                fingerprint=new_value,
                reason="first fetch — no prior record",
                response=response,
            )

        # Compare against stored fingerprint
        changed = new_value != existing.fingerprint_value

        # Always update last_fetched; only update last_changed if content differs
        self.records[url] = FingerprintRecord(
            url=url,
            fingerprint_method=strategy,
            fingerprint_value=new_value,
            last_fetched=now,
            last_changed=now if changed else existing.last_changed,
            content_bytes=content_bytes,
        )

        if changed:
            reason = f"{strategy} changed: " f"{existing.fingerprint_value!r} → {new_value!r}"
        else:
            reason = f"{strategy} unchanged ({new_value!r})"

        return CheckResult(
            url=url,
            changed=changed,
            method=strategy,
            fingerprint=new_value,
            reason=reason,
            response=response if changed else None,
        )

    def last_changed(self, url: str) -> str | None:
        """Return the last_changed timestamp for a URL, or None if unseen."""
        rec = self.records.get(url)
        return rec.last_changed if rec else None

    def last_fetched(self, url: str) -> str | None:
        """Return the last_fetched timestamp for a URL, or None if unseen."""
        rec = self.records.get(url)
        return rec.last_fetched if rec else None

    def summary(self) -> dict:
        """
        Return a summary suitable for display in the UI.
        Shows the oldest last_changed across all tracked URLs — i.e. the
        'stalest' piece of content — as the overall 'last updated' date.
        """
        if not self.records:
            return {"last_fetched": None, "last_changed": None, "url_count": 0}

        all_fetched = [r.last_fetched for r in self.records.values()]
        all_changed = [r.last_changed for r in self.records.values()]

        return {
            "last_fetched": max(all_fetched),  # most recent check
            "last_changed": min(all_changed),  # oldest content (most stale)
            "url_count": len(self.records),
        }
