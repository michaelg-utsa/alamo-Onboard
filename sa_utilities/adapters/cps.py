"""
adapters/cps.py
---------------
CPS Energy adapter.

Responsibilities:
  1. Scrape the rates page to discover all PDF URLs
  2. Download each PDF
  3. Extract clean text via pdfplumber
  4. Return a list of SourceDocument objects

Usage:
    from sa_utilities.adapters.cps import CPSAdapter
    docs = CPSAdapter().fetch_all()
"""

import logging
import re
import time
from io import BytesIO

import pdfplumber
import requests
from bs4 import BeautifulSoup
from sa_utilities.config import CPS_EXTRA_PAGES, CPS_RATES_PAGE, CRAWL_DELAY, REQUEST_HEADERS
from sa_utilities.models import DocType, Source, SourceDocument
from sa_utilities.pipeline.fingerprinter import Fingerprinter

logger = logging.getLogger(__name__)

HEADERS = REQUEST_HEADERS

# Map substrings in PDF filenames/titles to DocType
_DOCTYPE_HINTS = {
    "rate": DocType.RATE,
    "pricing": DocType.RATE,
    "misc": DocType.FEE,
    "charges": DocType.FEE,
    "rules": DocType.POLICY,
    "terms": DocType.POLICY,
    "conditions": DocType.POLICY,
}


def _infer_doc_type(title: str) -> DocType:
    lower = title.lower()
    for hint, dtype in _DOCTYPE_HINTS.items():
        if hint in lower:
            return dtype
    return DocType.GENERAL


def _extract_effective_date(text: str) -> str | None:
    """Pull 'Effective Date: ...' or 'Effective: ...' from extracted text."""
    match = re.search(
        r"Effective(?:\s+Date)?[:\s]+([A-Za-z]+ \d{1,2},? \d{4})",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _fetch_html(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "html.parser")


def _discover_pdf_urls(rates_page_url: str) -> list[dict]:
    """
    Scrape the rates page and return a list of
    {"url": ..., "title": ...} dicts for every PDF link found.
    """
    from sa_utilities.config import CPS_EXCLUDED_PDFS

    logger.info(f"Discovering PDFs from: {rates_page_url}")
    soup = _fetch_html(rates_page_url)

    pdfs = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        filename = href.split("/")[-1]

        if filename in CPS_EXCLUDED_PDFS:
            logger.debug(f"  Skipping excluded PDF: {filename}")
            continue
        if not href.endswith(".pdf"):
            continue
        # Resolve relative URLs
        if href.startswith("/"):
            href = "https://www.cpsenergy.com" + href
        if href in seen:
            continue
        seen.add(href)
        title = a.get_text(strip=True) or href.split("/")[-1].replace(".pdf", "")
        pdfs.append({"url": href, "title": title})
        logger.debug(f"  Found PDF: {title}")

    logger.info(f"Discovered {len(pdfs)} PDFs")
    return pdfs


def _extract_pdf_text(content: bytes) -> str:
    """Extract all text from PDF bytes using pdfplumber."""
    full_text_parts = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text_parts.append(text.strip())
    return "\n\n".join(full_text_parts)


def _extract_html_content(soup: BeautifulSoup) -> str:
    """
    Extract meaningful text from a CPS HTML page.
    Strips nav, footer, login widgets, and transient alert banners.
    """
    for tag in soup.find_all(["nav", "footer", "header", "script", "style"]):
        tag.decompose()

    for tag in soup.find_all(
        ["div", "section"],
        class_=lambda c: c
        and any(kw in c for kw in ["alert", "banner", "notification", "emergency"]),
    ):
        tag.decompose()

    main = (
        soup.find("main")
        or soup.find("div", {"id": "maincontent"})
        or soup.find("div", {"class": lambda c: c and "content" in c})
        or soup.body
    )

    # Use get_text() on the whole container rather than tag-by-tag filtering.
    # The CPS assistance page uses div/span card structures that don't use
    # semantic heading tags, so tag-by-tag extraction silently drops them.
    if main:
        text = main.get_text(separator="\n", strip=True)
        # Filter out very short lines (nav remnants, icons, single words)
        lines = [line.strip() for line in text.splitlines()]
        meaningful = [line for line in lines if len(line) > 20]
        return "\n".join(meaningful)
    return ""


class CPSAdapter:
    """
    Fetches and extracts all rate/policy documents from CPS Energy.
    """

    def __init__(self, delay: float = CRAWL_DELAY["cps"]):
        """
        Args:
            delay: Seconds to wait between HTTP requests (be polite).
        """
        self.delay = delay

    def fetch_all(self) -> list[SourceDocument]:
        """
        Full pipeline: discover PDFs → download → extract → scrape extra HTML
        pages → return documents. Skips unchanged content via fingerprinting.
        """
        fingerprinter = Fingerprinter()
        documents = []

        # --- PDFs auto-discovered from the rates page ---
        pdf_list = _discover_pdf_urls(CPS_RATES_PAGE)
        for i, pdf_info in enumerate(pdf_list):
            if i > 0:
                time.sleep(self.delay)
            url = pdf_info["url"]
            title = pdf_info["title"]
            try:
                resp = requests.get(url, headers=HEADERS, timeout=30)
                result = fingerprinter.check(url, resp)
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                continue
            if not result.changed:
                logger.info(f"  — skipped (unchanged): {title}")
                continue
            logger.info(f"  ✓ changed ({result.reason}): {title}")
            try:
                text = _extract_pdf_text(resp.content)
            except Exception as e:
                logger.warning(f"Failed to extract {url}: {e}")
                continue
            if not text.strip():
                continue
            documents.append(
                SourceDocument(
                    source=Source.CPS,
                    doc_type=_infer_doc_type(title),
                    title=title,
                    url=url,
                    content=text,
                    effective_date=_extract_effective_date(text),
                    metadata={
                        "filename": url.split("/")[-1],
                        "last_changed": fingerprinter.last_changed(url),
                        "last_fetched": fingerprinter.last_fetched(url),
                    },
                )
            )

        # --- Extra HTML pages (signup, assistance, etc.) ---
        for page in CPS_EXTRA_PAGES:
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
            content = _extract_html_content(soup)
            if not content.strip():
                logger.warning(f"Empty content for {title}, skipping")
                continue
            documents.append(
                SourceDocument(
                    source=Source.CPS,
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
            )

        fingerprinter.save()
        logger.info(f"CPSAdapter: {len(documents)} documents updated")
        return documents
