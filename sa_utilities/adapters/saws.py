"""
adapters/saws.py
----------------
SAWS (San Antonio Water System) adapter.

All content is static HTML - no PDF extraction needed.

Pages scraped:
  - Residential rates (HTML tables → structured text)
  - Water supply fee
  - Special services fees
  - Start service / signup form (fields → slot-fill schema)

Usage:
    from sa_utilities.adapters.saws import SAWSAdapter
    docs = SAWSAdapter().fetch_all()
"""

import logging
import time

import requests
from bs4 import BeautifulSoup
from sa_utilities.config import CRAWL_DELAY, REQUEST_HEADERS, SAWS_PAGES
from sa_utilities.models import DocType, Source, SourceDocument
from sa_utilities.pipeline.fingerprinter import Fingerprinter

logger = logging.getLogger(__name__)

BASE_URL = "https://www.saws.org"
HEADERS = REQUEST_HEADERS
PAGES = SAWS_PAGES


def _fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "html.parser")


def _table_to_text(table) -> str:
    """
    Convert an HTML table to a readable plain-text representation.
    Handles merged header rows cleanly.
    """
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
        # Skip rows that are entirely empty or whitespace
        if any(c.strip() for c in cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _extract_signup_form_fields(soup: BeautifulSoup) -> str:
    """
    Extract the SAWS new-service form fields and present them as a
    structured plain-text slot schema for the FSM.
    """
    lines = ["SAWS New Service Application — Required Fields:\n"]

    # Grab all label elements as field names
    for label in soup.find_all(["label", "li"]):
        text = label.get_text(" ", strip=True)
        # Filter out nav/footer noise - keep form-relevant content
        if any(
            kw in text.lower()
            for kw in [
                "required",
                "address",
                "license",
                "name",
                "phone",
                "date",
                "email",
                "military",
                "birth",
                "own",
                "rent",
                "mailing",
                "id",
                "passport",
                "state",
            ]
        ):
            if len(text) > 4 and len(text) < 200:
                lines.append(f"  • {text}")

    # Also capture key constraint text
    for p in soup.find_all(["p", "em", "small"]):
        text = p.get_text(" ", strip=True)
        if "business days" in text.lower() or "deposit" in text.lower():
            lines.append(f"\nNote: {text}")

    return "\n".join(lines)


def _extract_main_content(soup: BeautifulSoup, url: str, doc_type: DocType) -> str:
    """
    Extract the meaningful content from a SAWS page, handling:
    - Rate tables → plain text table representation
    - Signup forms → structured field list
    - General content → paragraph text
    """
    # Find the main content area (SAWS uses <main> or a content div)
    main = (
        soup.find("main")
        or soup.find("div", {"id": "main-cnt"})
        or soup.find("div", {"class": lambda c: c and "content" in c})
        or soup.body
    )

    parts = []

    # Extract page heading
    h2 = main.find("h2") if main else None
    if h2:
        parts.append(f"# {h2.get_text(strip=True)}\n")

    # Special handling for signup form pages
    if doc_type == DocType.SIGNUP and "form" in url:
        parts.append(_extract_signup_form_fields(soup))
        return "\n".join(parts)

    # Extract tables (rate pages)
    tables = main.find_all("table") if main else []
    for table in tables:
        # Get caption or preceding heading as table title
        caption = table.find("caption")
        if caption:
            parts.append(f"\n## {caption.get_text(strip=True)}")
        parts.append(_table_to_text(table))
        parts.append("")  # Blank line separator

    # Extract paragraph text (policies, notes, conditions)
    for tag in (main or soup).find_all(["p", "li", "h3", "h4"]):
        # Skip nav/footer items
        if tag.find_parent(["nav", "footer", "header"]):
            continue
        text = tag.get_text(" ", strip=True)
        if text and len(text) > 20:
            parts.append(text)

    return "\n".join(parts)


class SAWSAdapter:
    """
    Fetches and extracts all rate/policy/signup content from SAWS.
    """

    def __init__(self, delay: float = CRAWL_DELAY["saws"]):
        self.delay = delay

    def fetch_all(self) -> list[SourceDocument]:
        fingerprinter = Fingerprinter()
        documents = []

        for i, page in enumerate(PAGES):
            if i > 0:
                time.sleep(self.delay)

            url = page["url"]
            title = page["title"]
            doc_type = page["doc_type"]

            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                result = fingerprinter.check(url, resp)
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                continue

            if not result.changed:
                logger.info(f"  — skipped (unchanged): {title}")
                continue

            logger.info(f"  ✓ changed ({result.reason}): {title}")

            soup = BeautifulSoup(resp.content, "html.parser")
            content = _extract_main_content(soup, url, doc_type)

            if not content.strip():
                logger.warning(f"Empty content for {title}, skipping")
                continue

            doc = SourceDocument(
                source=Source.SAWS,
                doc_type=doc_type,
                title=title,
                url=url,
                content=content,
                metadata={
                    **page.get("metadata", {}),
                    "last_changed": fingerprinter.last_changed(url),
                    "last_fetched": fingerprinter.last_fetched(url),
                },
            )
            documents.append(doc)

        fingerprinter.save()
        logger.info(f"SAWSAdapter: {len(documents)} documents updated")
        return documents
