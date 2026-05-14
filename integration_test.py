#!/usr/bin/env python3
"""
integration_test.py
-------------------
End-to-end test of the SA Utilities pipeline.

Runs the full pipeline against live websites, then verifies that
the output chunks contain the information the agent needs to answer
real user questions.

Usage:
    pip install requests beautifulsoup4 pdfplumber
    python integration_test.py

    # Skip re-fetching if you've already run once:
    python integration_test.py --no-fetch

    # Test a single source:
    python integration_test.py --sources cps
"""

import sys
import json
import argparse
from pathlib import Path
from collections import Counter, defaultdict

# -----------------------------------------------------------------------
# Allow running from any directory
# -----------------------------------------------------------------------
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from sa_utilities.pipeline.runner import run
from sa_utilities.models import Source, DocType


# -----------------------------------------------------------------------
# Verification cases
# Each entry is: (description, doc_type_filter, required_terms)
# The test passes if ALL required_terms appear somewhere in the chunks
# that match the doc_type_filter (or any chunk if filter is None).
# -----------------------------------------------------------------------


# CHECKS = [
#     # --- CPS rates ---
#     (
#         "CPS residential electric rate monthly charge",
#         DocType.RATE,
#         ["9.50", "Service Availability Charge"],
#     ),
#     (
#         "CPS residential electric energy charge per kWh",
#         DocType.RATE,
#         ["0.07503", "kWh"],
#     ),
#     (
#         "CPS peak capacity charge (summer only)",
#         DocType.RATE,
#         ["0.02150", "600 kWh"],
#     ),
#     (
#         "CPS all-electric non-summer tier discount",
#         DocType.RATE,
#         ["0.06429"],
#     ),
#     (
#         "CPS late payment charge",
#         DocType.RATE,
#         ["late payment", "2 percent"],
#     ),

#     # --- CPS fees ---
#     (
#         "CPS reconnection fee at meter",
#         DocType.FEE,
#         ["24.00", "Regular Work Hours"],
#     ),
#     (
#         "CPS returned payment fee",
#         DocType.FEE,
#         ["25.00", "Returned Payment"],
#     ),
#     (
#         "CPS disconnection notice fee",
#         DocType.FEE,
#         ["4.00", "Disconnection Notice"],
#     ),

#     # --- CPS policy (signup requirements) ---
#     (
#         "CPS required ID types for new service",
#         DocType.POLICY,
#         ["driver's license", "social security"],
#     ),
#     (
#         "CPS proof of occupancy requirement",
#         DocType.POLICY,
#         ["proof of occupancy"],
#     ),
#     (
#         "CPS security deposit rules",
#         DocType.POLICY,
#         ["security deposit"],
#     ),
#     (
#         "CPS deposit waiver for active military",
#         DocType.POLICY,
#         ["Armed Forces", "waiver"],
#     ),

#     # --- CPS assistance ---
#     (
#         "CPS Affordability Discount Program",
#         DocType.ASSISTANCE,
#         ["Affordability", "low-income"],  # was ["Affordability Discount"]
#     ),
#     (
#         "CPS REAP program for low-income families",
#         DocType.ASSISTANCE,
#         ["REAP"],
#     ),
#     (
#         "CPS Critical Care Program for medical equipment",
#         DocType.ASSISTANCE,
#         ["Critical Care", "medical equipment"],  # was ["Critical Care"]
#     ),
#     (
#         "CPS Burned Veterans Discount",
#         DocType.ASSISTANCE,
#         ["Veterans", "Discount"],
#     ),

#     # --- SAWS rates ---
#     (
#         "SAWS residential water rate per 1000 gallons (first tier)",
#         DocType.RATE,
#         ["0.907"],
#     ),
#     (
#         "SAWS service availability charge for 5/8 inch meter",
#         DocType.RATE,
#         ["9.00", "5/8"],
#     ),
#     (
#         "SAWS sewer availability charge",
#         DocType.RATE,
#         ["10.00", "sewer"],
#     ),
#     (
#         "SAWS winter averaging for sewer billing",
#         DocType.RATE,
#         ["winter", "5,985"],
#     ),

#     # --- SAWS signup ---
#     (
#         "SAWS new service move-in date minimum",
#         DocType.SIGNUP,
#         ["5 business days"],
#     ),
#     (
#         "SAWS required ID for new service",
#         DocType.SIGNUP,
#         ["driver's license", "date of birth"],
#     ),
#     (
#         "SAWS deposit required for new service",
#         DocType.SIGNUP,
#         ["deposit"],
#     ),
#     (
#         "SAWS active military deposit waiver",
#         DocType.SIGNUP,
#         ["military"],
#     ),

#     # --- SAWS assistance ---
#     (
#         "SAWS Uplift program overview",
#         DocType.ASSISTANCE,
#         ["Uplift"],
#     ),
#     (
#         "SAWS Uplift eligibility: income and home value",
#         DocType.ASSISTANCE,
#         ["income", "300,000"],
#     ),

#     # --- CoSA assistance ---
#     (
#         "CoSA DHS utility assistance income threshold",
#         DocType.ASSISTANCE,
#         ["150%", "Federal Poverty"],
#     ),
#     (
#         "CoSA DHS utility assistance priority groups",
#         DocType.ASSISTANCE,
#         ["disability", "60 years"],
#     ),
#     (
#         "CoSA DHS application processing time",
#         DocType.ASSISTANCE,
#         ["30 days"],
#     ),
# ]


CHECKS = [
    # --- CPS rates ---
    (
        "CPS residential electric rate monthly charge",
        Source.CPS, DocType.RATE,
        ["9.50", "Service Availability Charge"],
    ),
    (
        "CPS residential electric energy charge per kWh",
        Source.CPS, DocType.RATE,
        ["0.07503", "kWh"],
    ),
    (
        "CPS peak capacity charge (summer only)",
        Source.CPS, DocType.RATE,
        ["0.02150", "600 kWh"],
    ),
    (
        "CPS all-electric non-summer tier discount",
        Source.CPS, DocType.RATE,
        ["0.06429"],
    ),
    (
        "CPS late payment charge",
        Source.CPS, DocType.RATE,
        ["late payment", "2 percent"],
    ),

    # --- CPS fees ---
    (
        "CPS reconnection fee at meter",
        Source.CPS, DocType.FEE,
        ["24.00", "Regular Work Hours"],
    ),
    (
        "CPS returned payment fee",
        Source.CPS, DocType.FEE,
        ["25.00", "Returned Payment"],
    ),
    (
        "CPS disconnection notice fee",
        Source.CPS, DocType.FEE,
        ["4.00", "Disconnection Notice"],
    ),

    # --- CPS policy ---
    (
        "CPS required ID types for new service",
        Source.CPS, DocType.POLICY,
        ["driver's license", "social security"],
    ),
    (
        "CPS proof of occupancy requirement",
        Source.CPS, DocType.POLICY,
        ["proof of occupancy"],
    ),
    (
        "CPS security deposit rules",
        Source.CPS, DocType.POLICY,
        ["security deposit"],
    ),
    (
        "CPS deposit waiver for active military",
        Source.CPS, DocType.POLICY,
        ["Armed Forces", "waiver"],
    ),

    # --- CPS assistance ---
    (
        "CPS Affordability Discount Program",
        Source.CPS, DocType.ASSISTANCE,
        ["Affordability", "low-income"],
    ),
    (
        "CPS REAP program for low-income families",
        Source.CPS, DocType.ASSISTANCE,
        ["REAP"],
    ),
    (
        "CPS Critical Care Program for medical equipment",
        Source.CPS, DocType.ASSISTANCE,
        ["Critical Care"],
    ),
    (
        "CPS Burned Veterans Discount",
        Source.CPS, DocType.ASSISTANCE,
        ["Veterans", "Discount"],
    ),

    # --- SAWS rates ---
    (
        "SAWS residential water rate per 1000 gallons (first tier)",
        Source.SAWS, DocType.RATE,
        ["0.907"],
    ),
    (
        "SAWS service availability charge for 5/8 inch meter",
        Source.SAWS, DocType.RATE,
        ["9.00", "5/8"],
    ),
    (
        "SAWS sewer availability charge",
        Source.SAWS, DocType.RATE,
        ["10.00", "sewer"],
    ),
    (
        "SAWS winter averaging for sewer billing",
        Source.SAWS, DocType.RATE,
        ["winter", "5,985"],
    ),

    # --- SAWS signup ---
    (
        "SAWS new service move-in date minimum",
        Source.SAWS, DocType.SIGNUP,
        ["5 business days"],
    ),
    (
        "SAWS required ID for new service",
        Source.SAWS, DocType.SIGNUP,
        ["driver's license", "date of birth"],
    ),
    (
        "SAWS deposit required for new service",
        Source.SAWS, DocType.SIGNUP,
        ["deposit"],
    ),
    (
        "SAWS active military deposit waiver",
        Source.SAWS, DocType.SIGNUP,
        ["military"],
    ),

    # --- SAWS assistance ---
    (
        "SAWS Uplift program overview",
        Source.SAWS, DocType.ASSISTANCE,
        ["Uplift"],
    ),
    (
        "SAWS Uplift eligibility: income and home value",
        Source.SAWS, DocType.ASSISTANCE,
        ["income", "300,000"],
    ),

    # --- CoSA assistance ---
    (
        "CoSA DHS utility assistance income threshold",
        Source.COSA, DocType.ASSISTANCE,
        ["150%", "Federal Poverty"],
    ),
    (
        "CoSA DHS utility assistance priority groups",
        Source.COSA, DocType.ASSISTANCE,
        ["disability", "60 years"],
    ),
    (
        "CoSA DHS application processing time",
        Source.COSA, DocType.ASSISTANCE,
        ["30 days"],
    ),

    # --- CoSA solid waste ---
    (
        "CoSA solid waste monthly fee for small cart",
        Source.COSA, DocType.FEE,
        ["14.76", "48 gal"],
    ),
    (
        "CoSA recycling contamination fee",
        Source.COSA, DocType.FEE,
        ["25", "Contamination"],
    ),
    (
        "CoSA recycling cart accepted materials",
        Source.COSA, DocType.GENERAL,
        ["cardboard", "aluminum"],
    ),
]


# def search_chunks(chunks, doc_type_filter, required_terms):
#     """Return True if all required_terms appear in the filtered chunk set."""
#     if doc_type_filter is not None:
#         subset = [c for c in chunks if c.doc_type == doc_type_filter]
#     else:
#         subset = chunks

#     combined = " ".join(c.text for c in subset).lower()
#     return all(term.lower() in combined for term in required_terms)


# def find_missing(chunks, doc_type_filter, required_terms):
#     """Return which required_terms are missing from the filtered chunks."""
#     if doc_type_filter is not None:
#         subset = [c for c in chunks if c.doc_type == doc_type_filter]
#     else:
#         subset = chunks
#     combined = " ".join(c.text for c in subset).lower()
#     return [t for t in required_terms if t.lower() not in combined]


def search_chunks(chunks, source_filter, doc_type_filter, required_terms):
    subset = chunks
    if source_filter:
        subset = [c for c in subset if c.source == source_filter]
    if doc_type_filter:
        subset = [c for c in subset if c.doc_type == doc_type_filter]
    combined = " ".join(c.text for c in subset).lower()
    return all(term.lower() in combined for term in required_terms)


def find_missing(chunks, source_filter, doc_type_filter, required_terms):
    subset = chunks
    if source_filter:
        subset = [c for c in subset if c.source == source_filter]
    if doc_type_filter:
        subset = [c for c in subset if c.doc_type == doc_type_filter]
    combined = " ".join(c.text for c in subset).lower()
    return [t for t in required_terms if t.lower() not in combined]




def print_header(text):
    print(f"\n{'=' * 60}")
    print(text)
    print('=' * 60)


def main():
    parser = argparse.ArgumentParser(description="Integration test for SA Utilities pipeline")
    parser.add_argument("--sources", nargs="+", choices=["cps", "saws", "cosa"],
                        help="Which sources to test (default: all)")
    parser.add_argument("--no-fetch", action="store_true",
                        help="Reload from saved JSON instead of fetching live")
    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Stage 1: Run the pipeline
    # -----------------------------------------------------------------------
    print_header("STAGE 1: Running pipeline")
    docs, chunks = run(sources=args.sources, no_fetch=args.no_fetch)

    if not docs:
        print("\nERROR: No documents produced. Check your internet connection and paths.")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Stage 2: Pipeline stats
    # -----------------------------------------------------------------------
    print_header("STAGE 2: Pipeline statistics")

    by_source   = Counter(d.source.value   for d in docs)
    by_doctype  = Counter(d.doc_type.value for d in docs)
    chunk_sizes = [len(c.text) for c in chunks]

    print(f"\n  Documents : {len(docs)}")
    print(f"  Chunks    : {len(chunks)}")
    if chunk_sizes:
        print(f"  Chunk size: min={min(chunk_sizes)}  avg={sum(chunk_sizes)//len(chunk_sizes)}  max={max(chunk_sizes)}")

    print(f"\n  By source:")
    for source, count in sorted(by_source.items()):
        print(f"    {source:<10} {count} documents")

    print(f"\n  By doc_type:")
    for dtype, count in sorted(by_doctype.items()):
        chunk_count = sum(1 for c in chunks if c.doc_type.value == dtype)
        print(f"    {dtype:<12} {count} documents → {chunk_count} chunks")

    print(f"\n  Documents fetched:")
    for doc in docs:
        changed = doc.metadata.get("last_changed", "unknown")
        print(f"    [{doc.source.value}/{doc.doc_type.value}] {doc.title}")
        print(f"      {doc.char_count():,} chars | last changed: {changed}")

    # -----------------------------------------------------------------------
    # Stage 3: Fingerprint summary
    # -----------------------------------------------------------------------
    fp_path = ROOT / "sa_utilities" / "data" / "raw" / "fingerprints.json"
    if fp_path.exists():
        print_header("STAGE 3: Fingerprint summary")
        with open(fp_path, encoding="utf-8") as f:
            fps = json.load(f)
        methods = Counter(v["fingerprint_method"] for v in fps.values())
        print(f"\n  Tracked URLs : {len(fps)}")
        print(f"  By method    : {dict(methods)}")
        print(f"\n  Sample records:")
        for url, data in list(fps.items())[:3]:
            short_url = url.split("/")[-1] or url.split("/")[-2]
            print(f"    {short_url[:50]}")
            print(f"      method      : {data['fingerprint_method']}")
            print(f"      last_fetched: {data['last_fetched']}")
            print(f"      last_changed: {data['last_changed']}")

    # -----------------------------------------------------------------------
    # Stage 4: Content verification
    # -----------------------------------------------------------------------
    print_header("STAGE 4: Content verification")
    print(f"\n  Running {len(CHECKS)} checks across all chunks...\n")

    # Filter checks to only the sources that were run
    active_sources = set(args.sources or ["cps", "saws", "cosa"])
    # source_map = {
    #     DocType.RATE:       ["cps", "saws"],
    #     DocType.FEE:        ["cps", "saws"],
    #     DocType.POLICY:     ["cps"],
    #     DocType.SIGNUP:     ["cps", "saws"],
    #     DocType.ASSISTANCE: ["cps", "saws", "cosa"],
    #     DocType.GENERAL:    ["cps", "saws", "cosa"],
    # }

    passed  = []
    failed  = []
    skipped = []


    # Load the full saved chunk index for verification
    # (current run may have skipped unchanged documents)
    chunks_path = ROOT / "sa_utilities" / "data" / "chunks" / "all_chunks.json"
    if chunks_path.exists():
        with open(chunks_path, encoding="utf-8") as f:
            saved = json.load(f)
        from sa_utilities.models import Chunk
        verify_chunks = []
        for c in saved:
            c.pop("embedding", None)
            c["source"]   = Source(c["source"])
            c["doc_type"] = DocType(c["doc_type"])
            verify_chunks.append(Chunk(**c))
        print(f"  Verifying against {len(verify_chunks)} saved chunks\n")
    else:
        verify_chunks = chunks
        print(f"  No saved index found — verifying against current run only\n")


    for description, source_filter, doc_type_filter, required_terms in CHECKS:
            if source_filter and source_filter.value not in active_sources:
                skipped.append(description)
                continue

            ok = search_chunks(verify_chunks, source_filter, doc_type_filter, required_terms)
            if ok:
                passed.append(description)
                print(f"  ✓ {description}")
            else:
                missing = find_missing(verify_chunks, source_filter, doc_type_filter, required_terms)
                failed.append((description, missing))
                print(f"  ✗ {description}")
                print(f"      Missing terms: {missing}")









    # for description, doc_type_filter, required_terms in CHECKS:
    #     # Skip checks for sources not in this run
    #     if doc_type_filter and not any(
    #         s in active_sources for s in source_map.get(doc_type_filter, [])
    #     ):
    #         skipped.append(description)
    #         continue

    #     ok = search_chunks(chunks, doc_type_filter, required_terms)
    #     if ok:
    #         passed.append(description)
    #         print(f"  ✓ {description}")
    #     else:
    #         missing = find_missing(chunks, doc_type_filter, required_terms)
    #         failed.append((description, missing))
    #         print(f"  ✗ {description}")
    #         print(f"      Missing terms: {missing}")

    # -----------------------------------------------------------------------
    # Stage 5: Summary
    # -----------------------------------------------------------------------
    print_header("STAGE 5: Summary")
    total = len(passed) + len(failed)
    print(f"\n  Passed  : {len(passed)}/{total}")
    print(f"  Failed  : {len(failed)}/{total}")
    if skipped:
        print(f"  Skipped : {len(skipped)} (sources not in this run)")

    if failed:
        print(f"\n  Failed checks:")
        for description, missing in failed:
            print(f"    • {description}")
            print(f"      Missing: {missing}")
        print(f"\n  Tip: if a check fails, the content may be behind a login")
        print(f"  wall, have changed on the source site, or the extractor")
        print(f"  may need adjustment for that page's HTML structure.")
        sys.exit(1)
    else:
        print(f"\n  All checks passed ✓")
        print(f"  The pipeline is extracting the expected content.")
        print(f"\n  Next step: run the embedder to build the vector index.")


if __name__ == "__main__":
    main()
