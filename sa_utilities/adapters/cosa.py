"""
adapters/cosa.py
----------------
City of San Antonio (CoSA) adapter.

Covers:
  - Solid Waste fees and collection info (311.sanantonio.gov)
  - San Antonio Public Library card signup (sapl.org)

Key insight: solid waste fees are billed THROUGH CPS Energy,
so this adapter also captures the cross-service relationship
that the agent needs to communicate to users.

Usage:
    from sa_utilities.adapters.cosa import CoSAAdapter
    docs = CoSAAdapter().fetch_all()
"""

import logging
import time

import requests
from bs4 import BeautifulSoup
from sa_utilities.config import COSA_PAGES, CRAWL_DELAY, REQUEST_HEADERS
from sa_utilities.models import Source, SourceDocument
from sa_utilities.pipeline.fingerprinter import Fingerprinter

logger = logging.getLogger(__name__)

HEADERS = REQUEST_HEADERS
PAGES = COSA_PAGES


def _fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "html.parser")


def _extract_content(soup: BeautifulSoup) -> str:
    """
    Extract meaningful text from CoSA / SAPL pages.
    Handles both prose content and HTML tables (fee schedules).
    """
    main = (
        soup.find("article")
        or soup.find("main")
        or soup.find(
            "div",
            {"class": lambda c: c and any(kw in c for kw in ["content", "article", "body", "kb-"])},
        )
        or soup.body
    )

    parts = []

    h1 = soup.find("h1")
    if h1:
        parts.append(f"# {h1.get_text(strip=True)}\n")

    for tag in (main or soup).find_all(["h2", "h3", "h4", "h5", "p", "li", "table"]):
        if tag.find_parent(["nav", "footer", "header", "aside"]):
            continue

        if tag.name == "table":
            # Convert table rows to pipe-separated text
            rows = []
            for tr in tag.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
                if any(c.strip() for c in cells):
                    rows.append(" | ".join(cells))
            if rows:
                parts.append("\n".join(rows))
        else:
            text = tag.get_text(" ", strip=True)
            if text and len(text) > 15:
                if tag.name in ["h2", "h3", "h4", "h5"]:
                    parts.append(f"\n## {text}")
                else:
                    parts.append(text)

    return "\n".join(parts)


class CoSAAdapter:
    """
    Fetches solid waste and library card content from City of San Antonio.
    """

    def __init__(self, delay: float = CRAWL_DELAY["cosa"]):
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
            content = _extract_content(soup)

            if not content.strip():
                logger.warning(f"Empty content for {title}, skipping")
                continue

            doc = SourceDocument(
                source=Source.COSA,
                doc_type=doc_type,
                title=title,
                url=url,
                content=content,
                metadata={
                    "last_changed": fingerprinter.last_changed(url),
                    "last_fetched": fingerprinter.last_fetched(url),
                },
            )
            documents.append(doc)

        fingerprinter.save()
        logger.info(f"CoSAAdapter: {len(documents)} documents updated")
        return documents
