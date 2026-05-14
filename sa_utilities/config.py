"""
config.py
---------
Central configuration for the SA Utilities ingestion pipeline.

This is the only file you should need to edit for:
  - Adding or removing pages to scrape
  - Tuning chunk sizes
  - Changing output paths
  - Adjusting crawl delays
"""

from pathlib import Path

from sa_utilities.models import DocType

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Root of the project (the sa_utilities/ folder)
PROJECT_ROOT = Path(__file__).parent

# Where raw extracted documents are saved (one JSON per source)
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Where chunked output is saved
CHUNK_DIR = PROJECT_ROOT / "data" / "chunks"


# ---------------------------------------------------------------------------
# Crawl settings
# ---------------------------------------------------------------------------

# Seconds to wait between HTTP requests per adapter (be polite to servers)
CRAWL_DELAY = {
    "cps": 1.0,
    "saws": 1.0,
    "cosa": 1.0,
}

# Shared request headers sent by all adapters
REQUEST_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (compatible; SAUtilitiesBot/1.0; " "+https://github.com/your-repo)")
}


# ---------------------------------------------------------------------------
# CPS Energy pages
# ---------------------------------------------------------------------------

CPS_RATES_PAGE = "https://www.cpsenergy.com/content/corporate/en/about-us/who-we-are/rates.html"

# Additional HTML pages to scrape from CPS (beyond the auto-discovered PDFs)
CPS_EXTRA_PAGES = [
    {
        "url": "https://www.cpsenergy.com/content/corporate/en/my-home/moving.html",
        "title": "CPS Energy — Moving (Start/Stop Service)",
        "doc_type": DocType.SIGNUP,
    },
    {
        "url": "https://www.cpsenergy.com/content/corporate/en/my-home/customer-assist-programs.html",
        "title": "CPS Energy Payment and Assistance Programs",
        "doc_type": DocType.ASSISTANCE,
        "metadata": {
            "programs": [
                "Affordability Discount Program",
                "Casa Verde",
                "Budget Payment Plan",
                "REAP",
                "Critical Care Program",
                "Disabled Citizens Billing Program",
                "Senior Citizen Billing Program",
                "Senior Citizen Late Fee Waiver",
                "Burned Veterans Discount",
                "First Responders Burn Discount",
            ],
            "eligibility_hints": ["income-based", "medical", "age", "veteran", "disability"],
            "contact": "210-353-2222",
            "update_frequency": "frequent",
        },
    },
    {
        "url": "https://www.cpsenergy.com/content/corporate/en/my-home/customer-assist-programs/Ineedhelpwithpayments.html",
        "title": "CPS Energy — Help with Payments",
        "doc_type": DocType.ASSISTANCE,
        "metadata": {
            "programs": ["Affordability Discount Program", "REAP"],
            "eligibility_hints": ["income-based"],
            "update_frequency": "frequent",
        },
    },
    {
        "url": "https://www.cpsenergy.com/content/corporate/en/my-home/customer-assist-programs/Ineedhelpduetospecialcircumstances.html",
        "title": "CPS Energy — Help for Special Circumstances",
        "doc_type": DocType.ASSISTANCE,
        "metadata": {
            "programs": [
                "Critical Care Program",
                "Disabled Citizens Billing Program",
                "Senior Citizen Billing Program",
                "Burned Veterans Discount",
                "First Responders Burn Discount",
            ],
            "eligibility_hints": ["medical", "age", "veteran", "disability"],
            "update_frequency": "frequent",
        },
    },
]


# ---------------------------------------------------------------------------
# SAWS pages
# ---------------------------------------------------------------------------

SAWS_PAGES = [
    {
        "url": "https://www.saws.org/service/water-sewer-rates/residential-water-service/",
        "title": "SAWS Residential Water & Sewer Rates",
        "doc_type": DocType.RATE,
    },
    {
        "url": "https://www.saws.org/service/water-sewer-rates/water-supply-fee/",
        "title": "SAWS Water Supply Fee",
        "doc_type": DocType.FEE,
    },
    {
        "url": "https://www.saws.org/service/water-sewer-rates/special-services-fees/",
        "title": "SAWS Special Services Fees",
        "doc_type": DocType.FEE,
    },
    {
        "url": "https://www.saws.org/service/start-stop-service/",
        "title": "SAWS Start or Stop Service",
        "doc_type": DocType.SIGNUP,
    },
    {
        "url": (
            "https://www.saws.org/customer-self-service-options/"
            "i-need-to-start-stop-saws-service/"
            "moving-into-new-property-form-page/"
        ),
        "title": "SAWS New Service Application Form",
        "doc_type": DocType.SIGNUP,
    },
    {
        "url": "https://www.saws.org/service/affordability-programs/",
        "title": "SAWS Uplift Affordability Programs",
        "doc_type": DocType.ASSISTANCE,
        "metadata": {
            "programs": ["SAWS Uplift"],
            "eligibility_hints": [
                "income-based",
                "residential",
                "home-value-under-300k",
            ],
            "contact": "210-233-2273",
            "contact_email": "uplift@saws.org",
            "application_url": "https://uplift.saws.org",
            "update_frequency": "frequent",
        },
    },
    {
        "url": "https://www.saws.org/service/water-sewer-rates/affordability-program-rates/",
        "title": "SAWS Uplift Affordability Program Rates",
        "doc_type": DocType.ASSISTANCE,
        "metadata": {
            "programs": ["SAWS Uplift"],
            "eligibility_hints": ["income-based", "residential"],
            "update_frequency": "frequent",
        },
    },
]


# ---------------------------------------------------------------------------
# City of San Antonio pages
# ---------------------------------------------------------------------------

COSA_PAGES = [
    {
        "url": "https://www.sa.gov/Directory/Departments/SWMD/Curbside-Service/Rates-Fees",
        "title": "City of San Antonio Solid Waste Rates and Fees",
        "doc_type": DocType.FEE,
    },
    {
        "url": "https://www.sa.gov/Directory/Departments/SWMD/Recycling-Organics/Recycling",
        "title": "City of San Antonio Curbside Recycling Collection",
        "doc_type": DocType.GENERAL,
    },
    {
        "url": "https://www.sa.gov/Directory/Departments/SWMD/Curbside-Service/Carts-Collections",
        "title": "City of San Antonio Carts and Collections",
        "doc_type": DocType.GENERAL,
    },
    {
        "url": "https://ask.mysapl.org/faq/141350",
        "title": "San Antonio Public Library Card — How to Get One",
        "doc_type": DocType.SIGNUP,
    },
    {
        "url": "https://www.sa.gov/Directory/Departments/DHS/Financial-Assistance/Utility-Assistance",
        "title": "City of San Antonio DHS Utility Assistance Program",
        "doc_type": DocType.ASSISTANCE,
        "metadata": {
            "programs": ["CoSA DHS Utility Assistance"],
            "eligibility_hints": [
                "income-based",
                "federal-poverty-level",
                "age",
                "disability",
                "children-under-17",
            ],
            "income_threshold_pct_fpl": 150,
            "contact": "210-207-8198",
            "application_url": "https://dhs.mendixcloud.com/",
            "processing_days": 30,
            "update_frequency": "frequent",
        },
    },
]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

# Max chunk size (chars) and overlap per document type.
# Smaller max_size = more precise retrieval of specific facts (rates, fees).
# Larger max_size = better context for policy/legal questions.
# Overlap ensures context isn't lost at chunk boundaries.
CHUNK_CONFIG = {
    DocType.RATE: {"max_size": 600, "overlap": 100},
    DocType.FEE: {"max_size": 600, "overlap": 100},
    DocType.SIGNUP: {"max_size": 800, "overlap": 150},
    DocType.POLICY: {"max_size": 800, "overlap": 150},
    DocType.FAQ: {"max_size": 800, "overlap": 150},
    DocType.ASSISTANCE: {"max_size": 800, "overlap": 150},
    DocType.GENERAL: {"max_size": 800, "overlap": 150},
}


# ---------------------------------------------------------------------------
# Embedding and vector store
# ---------------------------------------------------------------------------

# Embedding model — must be the same at index time AND query time.
# Changing this requires re-embedding everything from scratch.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers model name
EMBEDDING_DIM = 384  # output vector dimensions

# ChromaDB settings
CHROMA_COLLECTION = "sa_utilities"  # collection name inside ChromaDB
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"  # persistence directory

# Embedding batch size — how many chunks to embed in one forward pass.
# Larger = faster but more memory. 64 is safe for CPU with MiniLM.
EMBEDDING_BATCH_SIZE = 64

# PDFs to exclude from the CPS rates page auto-discovery.
# These are commercial/wholesale rates not relevant to residential users.
CPS_EXCLUDED_PDFS = {
    "2024_Rate_GeneralService.pdf",
    "2024_Rate_LargeLightingPowerService.pdf",
    "2024_Rate_ExtraLargePowerService.pdf",
    "2024_Super_Large_Power_Serv_Elec_Rate.pdf",
    "Industrial_High_Voltage_Service_ADA_21326.pdf",
    "2024_Rate_GasClassB.pdf",
    "2024_Rate_LargeVolumeGas.pdf",
    "2024_Compression_Station_for_Vehicles_(CSV)_Gas_Rate.pdf",
    "2024_Gas_Rate_for_Which_No_Other_Rate_Applies_(Class%20A).pdf",
    "WDSTariff091722.pdf",
    "BrattleGroupCostofServiceMarch2023.pdf",
}
