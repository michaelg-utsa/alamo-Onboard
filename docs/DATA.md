# Data Documentation

## Overview

AlamoOnboard uses two categories of data: scraped web content from three San Antonio utility providers (used to build the knowledge base), and a hand-authored JSON file defining service signup forms.

---

## Knowledge Base Data

### Source 1 — CPS Energy

| Field | Value |
|---|---|
| Provider | CPS Energy (City Public Service Energy) |
| Source URL | https://www.cpsenergy.com |
| Content types | Rate schedules (PDF), fee pages (HTML), policy pages (HTML), signup info (HTML), assistance programs (HTML) |
| License | Public web content; no redistribution license stated. Content is used for informational retrieval only and is not redistributed. |
| Scrape date | Determined at index-build time by `sa_utilities/pipeline/fingerprinter.py` (`last_fetched` field) |
| Change detection | ETag / Last-Modified header, fallback to SHA256 content hash |
| Stored as | `sa_utilities/data/raw/cps_documents.json` (raw), `sa_utilities/data/chunks/all_chunks.json` (chunked), `sa_utilities/data/chroma/` (embedded) |

### Source 2 — SAWS (San Antonio Water System)

| Field | Value |
|---|---|
| Provider | San Antonio Water System |
| Source URL | https://www.saws.org |
| Content types | Rate tables (HTML), fee schedules (HTML), signup forms (HTML), affordability programs (HTML) |
| License | Public web content; no redistribution license stated. Used for informational retrieval only. |
| Scrape date | Determined at index-build time |
| Change detection | ETag / Last-Modified / SHA256 |
| Stored as | `sa_utilities/data/raw/saws_documents.json`, chunks, ChromaDB |

### Source 3 — City of San Antonio (CoSA)

| Field | Value |
|---|---|
| Provider | City of San Antonio — Solid Waste Management Department |
| Source URL | https://www.sa.gov |
| Content types | Solid waste rates (HTML), cart size information (HTML), 3-1-1 service pages (HTML) |
| License | Public web content; no redistribution license stated. Used for informational retrieval only. |
| Scrape date | Determined at index-build time |
| Change detection | ETag / Last-Modified / SHA256 |
| Stored as | `sa_utilities/data/raw/cosa_documents.json`, chunks, ChromaDB |

### Chunk Statistics (approximate, varies by scrape date)

| Source | Documents | Chunks |
|---|---|---|
| CPS Energy | ~15 | ~120 |
| SAWS | ~12 | ~95 |
| City of SA | ~8 | ~60 |
| **Total** | **~35** | **~275** |

---

## Form Schema Data

| Field | Value |
|---|---|
| File | `data/form_schemas.json` |
| Version | `0.1.0` |
| Author | Project team (hand-authored) |
| License | N/A (project-internal artifact) |
| Content | JSON definitions for three service signup forms: `cps_energy_start`, `saws_start`, `cosa_solid_waste` |
| Format | See `src/forms/schemas.py` — `FormSchema` and `FormField` dataclasses |

---

## User State Data

| Field | Value |
|---|---|
| File | `output/user_state.json` |
| Contents | User profile (name, address, contact), checklist status per service, active workflow state, conversation history (last 200 turns) |
| Persistence | Written on every agent turn that changes state |
| Privacy | Contains PII (name, address, email, phone); masked for secrets (SSN shown as `***-**-XXXX`) |
| Gitignore | `output/` is excluded from version control |

---

## Embedding Index

| Field | Value |
|---|---|
| Files | `output/index/index.faiss`, `output/index/meta.json` |
| Format | FAISS `IndexFlatIP` (inner-product over L2-normalized vectors = cosine similarity) |
| Dimension | 384 (matching `all-MiniLM-L6-v2`) |
| Built from | SA Utilities ChromaDB; rebuilt with `make download-data` or `python main.py --rebuild` |
| Gitignore | `output/` is excluded from version control |
