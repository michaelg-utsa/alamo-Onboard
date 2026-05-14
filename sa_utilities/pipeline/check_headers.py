#!/usr/bin/env python3
"""
check_headers.py
----------------
Run this locally to check which cache headers CPS, SAWS, and CoSA
servers send back. This determines which fingerprint strategy we use
for change detection.

Usage:
    pip install requests
    python check_headers.py

Paste the output back to Claude so the adapter can be implemented
with the right strategy for each URL.
"""

import hashlib

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (compatible; SAUtilitiesBot/1.0; " "+https://github.com/your-repo)")
}

URLS = [
    # CPS
    (
        "CPS Rates page (HTML)",
        "https://www.cpsenergy.com/content/corporate/en/about-us/who-we-are/rates.html",
    ),
    (
        "CPS Residential Electric Rate (PDF)",
        "https://www.cpsenergy.com/content/dam/corporate/en/Documents/2024_Rate_ResidentialElectric.pdf",
    ),
    (
        "CPS Terms & Conditions (PDF)",
        "https://www.cpsenergy.com/content/dam/corporate/en/Documents/Res_RulesandRegs.pdf",
    ),
    # SAWS
    (
        "SAWS Residential Rates (HTML)",
        "https://www.saws.org/service/water-sewer-rates/residential-water-service/",
    ),
    (
        "SAWS Start Service form (HTML)",
        "https://www.saws.org/customer-self-service-options/i-need-to-start-stop-saws-service/moving-into-new-property-form-page/",
    ),
    # CoSA
    (
        "CoSA Solid Waste Fees (HTML)",
        "https://311.sanantonio.gov/kb/docs/articles/graffiti-and-waste-collection/solid-waste-fees-and-charges",
    ),
    ("SAPL Library Card (HTML)", "https://ask.mysapl.org/faq/141350"),
]


def check_url(label: str, url: str) -> dict:
    result = {"label": label, "url": url}

    # --- Try HEAD first (fast, no body download) ---
    try:
        head = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        result["head_status"] = head.status_code
        result["etag"] = head.headers.get("ETag")
        result["last_modified"] = head.headers.get("Last-Modified")
        result["cache_control"] = head.headers.get("Cache-Control")
        result["head_ok"] = head.status_code == 200
    except Exception as e:
        result["head_status"] = f"ERROR: {e}"
        result["head_ok"] = False

    # --- Always do a full GET too (some servers block HEAD) ---
    try:
        get = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        result["get_status"] = get.status_code

        # GET headers may differ from HEAD (some servers only set them on GET)
        result["etag"] = result.get("etag") or get.headers.get("ETag")
        result["last_modified"] = result.get("last_modified") or get.headers.get("Last-Modified")
        result["cache_control"] = result.get("cache_control") or get.headers.get("Cache-Control")

        # Compute content hash as fallback fingerprint
        content = get.content
        result["content_hash"] = hashlib.sha256(content).hexdigest()[:16]
        result["content_bytes"] = len(content)
        result["get_ok"] = get.status_code == 200

        # Record all headers for completeness
        result["all_get_headers"] = dict(get.headers)

    except Exception as e:
        result["get_status"] = f"ERROR: {e}"
        result["get_ok"] = False

    # Determine which fingerprint strategy applies
    if result.get("etag"):
        result["fingerprint_strategy"] = "etag"
    elif result.get("last_modified"):
        result["fingerprint_strategy"] = "last-modified"
    else:
        result["fingerprint_strategy"] = "content-hash (fallback)"

    return result


def main():
    print("=" * 70)
    print("Cache Header Inspection Report")
    print("=" * 70)

    all_results = []
    for label, url in URLS:
        print(f"\nChecking: {label}")
        print(f"  URL: {url}")
        r = check_url(label, url)
        all_results.append(r)

        print(f"  HEAD status      : {r.get('head_status', 'skipped')}")
        print(f"  GET status       : {r.get('get_status', 'skipped')}")
        print(f"  ETag             : {r.get('etag') or '— not sent'}")
        print(f"  Last-Modified    : {r.get('last_modified') or '— not sent'}")
        print(f"  Cache-Control    : {r.get('cache_control') or '— not sent'}")
        print(
            f"  Content hash     : {r.get('content_hash', 'n/a')} "
            f"({r.get('content_bytes', 0):,} bytes)"
        )
        print(f"  → Fingerprint strategy: {r.get('fingerprint_strategy', 'unknown')}")

    print("\n\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    print(f"  {'Source':<45} {'ETag':^6} {'LastMod':^8} {'Strategy'}")
    print(f"  {'-'*45} {'-'*6} {'-'*8} {'-'*20}")
    for r in all_results:
        etag_flag = "✓" if r.get("etag") else "✗"
        lm_flag = "✓" if r.get("last_modified") else "✗"
        strategy = r.get("fingerprint_strategy", "unknown")
        print(f"  {r['label']:<45} {etag_flag:^6} {lm_flag:^8} {strategy}")

    print("\n\n" + "=" * 70)
    print("ALL GET HEADERS (for reference)")
    print("=" * 70)
    for r in all_results:
        print(f"\n[{r['label']}]")
        if "all_get_headers" in r:
            for k, v in sorted(r["all_get_headers"].items()):
                print(f"  {k}: {v}")
        else:
            print("  (no GET response)")

    print("\n\nPaste this full output back to Claude.")


if __name__ == "__main__":
    main()
