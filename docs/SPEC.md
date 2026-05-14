# AlamoOnboard — Project Specification

**Target model:** `claude-opus-4-5-20251101`, temperature 0  
**Purpose:** Reproduce the complete AlamoOnboard project from scratch.

---

## 1. Project Overview

AlamoOnboard is a San Antonio utilities onboarding assistant. It helps people who are moving to San Antonio set up CPS Energy (electric/gas), SAWS (water/sewer), and City of San Antonio Solid Waste services. It combines a RAG (retrieval-augmented generation) knowledge base, an LLM agent with tool calling, a step-by-step form workflow FSM, and a Gradio web UI.

The system is a prototype: forms collect data locally and do NOT actually submit to any provider.

---

## 2. Repository Layout

```
project_root/
├── main.py                         # CLI entry point
├── config.py                       # All env vars and path resolution
├── requirements.txt
├── data/
│   └── form_schemas.json           # Three service signup form definitions
├── output/                         # Auto-created at runtime
│   ├── user_state.json             # Persisted user state (checklist, profile, history)
│   ├── index/
│   │   ├── index.faiss             # FAISS vector index
│   │   └── meta.json              # Chunk metadata parallel to FAISS rows
│   └── logs/
├── sa_utilities/                   # Sibling data pipeline (separate package)
│   └── data/
│       ├── chunks/all_chunks.json  # Scraped/parsed chunk metadata
│       └── chroma/                 # ChromaDB persistent dir holding embeddings
└── src/
    ├── __init__.py
    ├── agent/
    │   ├── __init__.py
    │   ├── llm_client.py           # OpenAI-compatible chat client + demo stub
    │   ├── orchestrator.py         # AlamoAgent: top-level message router
    │   ├── prompts.py              # SYSTEM_PROMPT, TOOL_DEFINITIONS, grounding formatter
    │   └── tools.py                # ToolBox: executes tool calls
    ├── checklist/
    │   ├── __init__.py
    │   └── tracker.py              # ChecklistTracker, UserState, ChecklistItem
    ├── forms/
    │   ├── __init__.py
    │   ├── prefill.py              # Cross-form profile pre-fill logic
    │   ├── schemas.py              # FormSchema, FormField dataclasses + loader
    │   ├── validators.py           # Field validators (email, phone, SSN, dates, etc.)
    │   └── workflow.py             # FormWorkflow FSM, WorkflowState
    ├── indexer/
    │   ├── __init__.py
    │   ├── embedder.py             # Lazy sentence-transformers wrapper
    │   ├── loaders.py              # Reads SA Utilities chunks JSON + ChromaDB
    │   ├── retriever.py            # HybridRetriever: BM25 + FAISS + RRF
    │   └── vector_store.py         # FAISS IndexFlatIP with JSON metadata sidecar
    ├── ui/
    │   ├── __init__.py
    │   └── gradio_app.py           # Gradio Blocks UI
    └── utils/
        ├── __init__.py
        └── logging_utils.py        # get_logger helper
```

---

## 3. Configuration (`config.py`)

All configuration is read from environment variables with sensible defaults. No `.env` file is used; set vars in the shell or process environment.

| Variable | Default | Description |
|---|---|---|
| `ALAMO_OUTPUT_DIR` | `<project_root>/output` | Where indices, logs, and user state are written |
| `ALAMO_DATA_DIR` | `<project_root>/data` | Where `form_schemas.json` lives |
| `ALAMO_INDEX_DIR` | `<output>/index` | FAISS index subdirectory |
| `ALAMO_SAU_ROOT` | `<project_root>/sa_utilities` | Root of the SA Utilities sibling package |
| `ALAMO_SAU_CHUNKS` | `<sau_root>/data/chunks/all_chunks.json` | SA Utilities chunk metadata file |
| `ALAMO_SAU_CHROMA` | `<sau_root>/data/chroma` | SA Utilities ChromaDB directory |
| `ALAMO_SAU_COLLECTION` | `sa_utilities` | ChromaDB collection name |
| `ALAMO_USER_STATE` | `<output>/user_state.json` | Persisted user state file |
| `ALAMO_EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model ID |
| `ALAMO_EMBED_DIM` | `384` | Embedding dimension (must match model) |
| `ALAMO_LLM_MODEL` | `llama-3.3-70b-instruct-awq` | Model name for OpenAI-compatible endpoint |
| `ALAMO_LLM_BASE_URL` | _(none)_ | Base URL for OpenAI-compatible endpoint |
| `ALAMO_LLM_API_KEY` | falls back to `OPENAI_API_KEY` | API key |
| `ALAMO_DEMO_MODE` | `"0"` | Set `"1"` to force no-LLM rule-based mode |
| `ALAMO_TOP_K` | `5` | Number of passages returned per retrieval call |

`DEMO_MODE` is automatically `True` when no API key is present (either key env var is unset or empty).

`config.py` also exposes a `banner()` function returning a one-line config summary string for logging.

All directory paths are created with `mkdir(parents=True, exist_ok=True)` at import time.

---

## 4. Dependencies (`requirements.txt`)

```
gradio>=6.0
openai>=1.40,<2.0
sentence-transformers>=2.7
faiss-cpu>=1.8
rank-bm25>=0.2.2
numpy>=1.26
chromadb>=0.5
huggingface_hub>=1.0
typing-extensions>=4.10
requests>=2.32
beautifulsoup4>=4.12
pdfplumber>=0.11
```

`chromadb`, `requests`, `beautifulsoup4`, `pdfplumber` are only needed at index-build time. The runtime does not touch ChromaDB after the FAISS index is built.

---

## 5. Entry Point (`main.py`)

```
python main.py            # build index if missing, then launch Gradio UI
python main.py --rebuild  # force rebuild of index from SA Utilities output
python main.py --cli      # text-only REPL instead of Gradio
```

`main.py` calls `HybridRetriever().load()` first; if it returns `False` (no on-disk index), it calls `retriever.build_from_sa_utilities()`. Then it either launches `src.ui.gradio_app.main()` or runs a simple `input()` REPL.

The CLI REPL creates an `AlamoAgent`, prints `banner()`, and loops on `input("you> ")`, calling `agent.handle_user_message()` and printing `reply.text`.

---

## 6. Data Layer

### 6.1 `src/indexer/embedder.py` — Lazy Embedder

```python
class Embedder:
    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name
        self._model = None  # lazy — not loaded until first .encode()

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def encode(self, texts: Iterable[str], normalize: bool = True) -> np.ndarray:
        # Returns (N, dim) float32 array, normalized by default
```

The model is NOT loaded when `Embedder()` is instantiated. It loads on the first call to `.encode()`. This is intentional — the UI renders before the model download starts. The UI forces the download via `agent.retriever.embedder.encode(["warmup"])` inside the `app.load()` event handler so the loading message is visible while it happens.

### 6.2 `src/indexer/vector_store.py` — FAISS VectorStore

Uses `faiss.IndexFlatIP` (inner-product, which equals cosine similarity on normalized vectors).

Stored as two files:
- `output/index/index.faiss` — the FAISS binary
- `output/index/meta.json` — JSON list of chunk metadata dicts, parallel to FAISS rows

Each metadata dict has keys: `doc_id`, `source`, `title`, `url`, `text`, `doc_type`, `chunk_index`.

```python
class VectorStore:
    def build(self, vectors: np.ndarray, metadata: Sequence[dict]) -> None: ...
    def save(self) -> None: ...
    def load(self) -> bool: ...  # returns False if files missing
    def search(self, query_vec: np.ndarray, k: int = 5) -> list[tuple[float, dict]]: ...
    def __len__(self) -> int: ...
```

### 6.3 `src/indexer/loaders.py` — SA Utilities Adapter

This is the seam between the SA Utilities sibling pipeline and our retrieval layer. It reads:
1. `sa_utilities/data/chunks/all_chunks.json` — chunk metadata
2. `sa_utilities/data/chroma/` — ChromaDB with embeddings keyed by `chunk_id`

Source labels from SA Utilities (`"cps"`, `"saws"`, `"cosa"`) are normalized to display names (`"CPS Energy"`, `"SAWS"`, `"City of San Antonio"`). These display names are used throughout the system prompt, citations, and `source_filter` arguments.

Key function:
```python
def load_sa_utilities_data(...) -> tuple[list[IndexedChunk], np.ndarray]:
    # Returns (chunks, L2-normalized float32 vectors)
```

Deduplicates chunks by `chunk_id` (keeps first occurrence). Validates embedding dimension against `EMBED_DIM`. L2-normalizes all vectors.

`IndexedChunk` dataclass: `chunk_id`, `source`, `title`, `url`, `text`, `doc_type`, `chunk_index`. `.as_dict()` returns the metadata dict shape the rest of the system expects.

### 6.4 `src/indexer/retriever.py` — HybridRetriever

BM25 keyword search + FAISS dense search, fused with Reciprocal Rank Fusion (RRF, k=60).

```python
class HybridRetriever:
    def __init__(self): ...
    def build_from_sa_utilities(self) -> None: ...
    def load(self) -> bool: ...
    def search(self, query: str, k: int = TOP_K, source_filter: Iterable[str] | None = None) -> list[RetrievedPassage]: ...
```

**Search algorithm:**
1. Encode query with `Embedder` (lazy load triggers here if first search)
2. Dense search: `VectorStore.search(q_vec, k=k*2)`
3. BM25 search: `BM25Okapi.get_scores(tokenized_query)`, take top `k*2`
4. RRF: for each hit from either list, accumulate `1.0 / (60 + rank)`
5. Sort by RRF score descending
6. If `source_filter` is set, skip chunks whose `source` is not in the filter set
7. Return first `k` results as `RetrievedPassage` dataclasses

`RetrievedPassage` has: `text`, `title`, `source`, `url`, `score`, `citation()` method.

BM25 tokenizer: lowercase, keep only alphanumeric, split on whitespace.

---

## 7. Form System

### 7.1 `data/form_schemas.json`

Top-level structure:
```json
{
  "version": "0.1.0",
  "forms": {
    "<form_key>": { <FormSchema object> }
  }
}
```

Three forms are defined:

**`cps_energy_start`** (`service_id: "cps_energy"`)  
Provider: CPS Energy  
Submit URL: `https://www.cpsenergy.com/startservice`  
Lead time: 2 business days  
14 fields (in order):

| name | label | type | required | validator | prefill_from | default |
|---|---|---|---|---|---|---|
| first_name | First name | text | true | — | user.first_name | — |
| last_name | Last name | text | true | — | user.last_name | — |
| date_of_birth | Date of birth | date | true | date_of_birth | user.date_of_birth | — |
| ssn_or_dl | SSN or driver license number | secret | true | ssn_or_dl | — | — |
| email | Email | email | true | email | user.email | — |
| phone | Phone | phone | true | phone_us | user.phone | — |
| service_address | Service address | address | true | address | user.service_address | — |
| service_city | City | text | true | — | user.service_city | "San Antonio" |
| service_state | State | text | true | — | — | "TX" |
| service_zip | ZIP | text | true | zip_us | user.service_zip | — |
| requested_start_date | Requested start date | date | true | lead_time_2bd | — | — |
| is_military_relocation | Active-duty military relocating to San Antonio? | boolean | false | — | — | false |
| wants_paperless | Enroll in Manage My Account paperless billing? | boolean | false | — | — | true |
| wants_budget_billing | Enroll in Budget Payment Plan? | boolean | false | — | — | false |

Completion message: "Once submitted, CPS Energy will email a confirmation on the day service is scheduled to start. If a deposit is required, they will contact you by phone or email."

---

**`saws_start`** (`service_id: "saws"`)  
Provider: San Antonio Water System  
Submit URL: `https://www.saws.org/service/start-stop-service/`  
Lead time: 5 business days  
14 fields (in order):

| name | label | type | required | validator | prefill_from | default |
|---|---|---|---|---|---|---|
| first_name | First name | text | true | — | user.first_name | — |
| last_name | Last name | text | true | — | user.last_name | — |
| date_of_birth | Date of birth | date | true | date_of_birth | user.date_of_birth | — |
| ssn_last4 | Last 4 of SSN | secret | true | ssn_last4 | — | — |
| email | Email | email | true | email | user.email | — |
| phone | Phone | phone | true | phone_us | user.phone | — |
| service_address | Service address | address | true | address | user.service_address | — |
| service_city | City | text | true | — | user.service_city | "San Antonio" |
| service_state | State | text | true | — | — | "TX" |
| service_zip | ZIP | text | true | zip_us | user.service_zip | — |
| requested_start_date | Requested start date | date | true | lead_time_5bd | — | — |
| residency_proof_type | Proof of residency type | select | true | — | — | — |
| letter_of_credit_available | Have a letter of credit from a previous water utility? | boolean | false | — | — | false |
| is_dv_survivor_waiver | Apply for the Domestic Violence Deposit Waiver? | boolean | false | — | — | false |

`residency_proof_type` options: `["Lease agreement", "Closing documents", "Utility bill in your name"]`

Completion message: "Bring a copy of your photo ID and your proof of residency to the SAWS portal upload page when prompted. A SAWS technician will visit on the start date to take the first meter reading."

---

**`cosa_solid_waste`** (`service_id: "cosa_solid_waste"`)  
Provider: City of San Antonio Solid Waste Management  
Submit URL: `https://www.sa.gov/Directory/Departments/SWMD`  
Lead time: 0 days  
10 fields (in order):

| name | label | type | required | validator | prefill_from | default |
|---|---|---|---|---|---|---|
| first_name | First name | text | true | — | user.first_name | — |
| last_name | Last name | text | true | — | user.last_name | — |
| phone | Phone | phone | true | phone_us | user.phone | — |
| service_address | Service address | address | true | address | user.service_address | — |
| service_zip | ZIP | text | true | zip_us | user.service_zip | — |
| cps_account_number | CPS Energy account number (if known) | text | false | cps_account | — | — |
| carts_present | Are the brown, blue, and green carts already at the property? | select | true | — | — | — |
| preferred_brown_cart_size | Preferred brown trash cart size | select | true | — | — | "Medium (64 gallon, ~$20.26/mo)" |
| wants_collection_day_lookup | Look up your weekly collection day now? | boolean | false | — | — | true |
| wants_text_alerts | Sign up for cart-serviced text notifications? | boolean | false | — | — | false |

`carts_present` options: `["Yes, all three", "Only some of them", "No carts at all", "Not sure yet"]`  
`preferred_brown_cart_size` options: `["Small (48 gallon, ~$14.76/mo)", "Medium (64 gallon, ~$20.26/mo)", "Large (96 gallon, ~$30.75/mo)"]`

Completion message: "If any carts are missing or the wrong size, a 3-1-1 request will be queued for you. Set carts at the curb by 7:00 AM on your collection day, with at least three feet of clearance."

### 7.2 `src/forms/schemas.py`

```python
@dataclass
class FormField:
    name: str; label: str; type: str; required: bool = False
    validator: str | None = None; prefill_from: str | None = None
    default: Any = None; options: list[str] = field(default_factory=list); help: str = ""

@dataclass
class FormSchema:
    service_id: str; title: str; provider: str; submit_url: str
    lead_time_days: int; description: str; fields: list[FormField]; completion_message: str

    @classmethod
    def from_dict(cls, d: dict) -> "FormSchema": ...

def load_schemas(path: Path = FORM_SCHEMAS_PATH) -> dict[str, FormSchema]:
    # Keyed by service_id (not form key)
```

### 7.3 `src/forms/validators.py`

All validators have signature `(value: str) -> tuple[bool, str, str]` — `(ok, cleaned_value, error_message)`.

Registry dict `VALIDATORS` maps name strings to functions:

| Validator name | What it accepts | Cleaned output |
|---|---|---|
| `email` | Any `x@y.z` shaped string | Lowercased |
| `phone_us` | 10 or 11-digit US number (any formatting) | `(NXX) NXX-XXXX` |
| `zip_us` | 5-digit or ZIP+4 | As-is |
| `address` | Starts with number, has alpha chars | As-is stripped |
| `ssn_or_dl` | 9-digit SSN or 5–13 alphanumeric DL | `***-**-XXXX` or `DL ending XXXX` |
| `ssn_last4` | Exactly 4 digits | Digits only |
| `cps_account` | 9–16 digits (optional field) | Digits only |
| `lead_time_2bd` | Date ≥ 2 business days from today, not weekend | ISO date string |
| `lead_time_5bd` | Date ≥ 5 business days from today, not weekend | ISO date string |
| `date` | `YYYY-MM-DD`, `MM/DD/YYYY`, `MM-DD-YYYY`, `MM/DD/YY` | ISO date string |
| `date_of_birth` | Standard date formats OR a bare integer age (1–120) | ISO date string; integer age is converted to estimated birthdate (today minus N years) |

`validate(name, value)` dispatches by name; unknown names pass through unchanged.

Business day calculation: add N days one at a time, counting only Mon–Fri.

### 7.4 `src/forms/prefill.py`

```python
def prefill_form(schema: FormSchema, profile: dict) -> dict[str, Any]:
    # Resolves "user.field_name" dotted paths against profile dict
    # Falls back to field.default if profile value missing
    # Returns {field_name: value} for all fields that have a resolved value

def update_profile_from_form(profile: dict, schema: FormSchema, form_values: dict) -> dict:
    # Pushes non-secret form values back to profile["user"][key]
    # Only for fields with prefill_from starting "user."
    # Never writes secret-type fields to profile

def field_summary(field: FormField, value: Any) -> str:
    # Returns "  - Label: value" string for the summary screen
    # Secret type shows masked form (starts with "***" or "DL ") or "***hidden***"
```

Path resolver: dotted path `"user.first_name"` resolves by looking up `profile["user"]["first_name"]`. First segment must be `"user"`.

### 7.5 `src/forms/workflow.py` — Form FSM

```python
@dataclass
class WorkflowState:
    service_id: str
    current_field_index: int = 0
    values: dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict: ...       # asdict()
    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowState": ...
```

```python
class FormWorkflow:
    def __init__(self, schema: FormSchema, state: WorkflowState | None = None): ...

    def start(self, profile: dict) -> str:
        # Calls prefill_form, sets values via setdefault, returns _intro_message()

    def is_complete(self) -> bool:
        return self.state.completed

    @property
    def current_field(self) -> FormField | None:
        # Returns schema.fields[current_field_index], or None if past end

    def prompt_for_current_field(self) -> str:
        # Returns formatted field prompt with pre-filled hint, help text, options

    def submit_value(self, raw_value: str) -> tuple[bool, str]:
        # Returns (advanced, message)
        # Handles: "keep" (use pre-filled), "skip" (if not required), boolean coercion,
        # select validation, named validator, required check
        # On success: stores cleaned value, advances index, returns next prompt or summary

    def keep_all(self) -> str:
        # Advances through all pre-filled fields in sequence, stops at first gap
        # Returns next prompt or summary

    def undo(self) -> str:
        # Decrements current_field_index, clears stored value and error for that field
        # Resets completed=False if we were on the summary
        # Returns "Went back. {prompt}"
        # Guard: if already at index 0, return "You're already on the first field — nothing to undo."

    def edit_field(self, field_name: str) -> str:
        # Matches by name or label (case-insensitive)
        # Sets current_field_index, sets completed=False
        # Returns field prompt

    def commit(self, profile: dict) -> dict:
        # Calls update_profile_from_form, returns updated profile
```

**Intro message format:**
```
### {title}

_Provider: {provider}_

{description}

I'll walk you through {N} fields. You can reply 'keep' to accept any pre-filled value or 'skip' to skip an optional field.

---

{first field prompt}
```

**Field prompt format:**
```
**{label}**[ (pre-filled hint)]
[_{help}_]
[Options: opt1, opt2, opt3]
[(Optional - reply 'skip' to leave blank.)]
```

Pre-fill hint for non-secret: `(we have '{value}' on file - reply 'keep' to use it)`  
Pre-fill hint for secret: `(a value is already on file - reply 'keep' to use it)`

**Summary message format:**
```
### Review: {title}

  - Label: value
  (one line per field, secrets masked)

Submit URL: {submit_url}

{completion_message}

Reply **submit** to mark this service complete, **edit <field>** to change a value, or **cancel** to abandon this workflow.
```

---

## 8. Checklist & User State

### 8.1 `src/checklist/tracker.py`

```python
@dataclass
class ChecklistItem:
    service_id: str; name: str; status: str  # pending|in_progress|completed|skipped
    lead_time_days: int; form_id: str
    completed_at: str | None = None; notes: str = ""

@dataclass
class UserState:
    profile: dict[str, Any] = field(default_factory=dict)
    checklist: list[ChecklistItem] = field(default_factory=list)
    active_workflow: dict | None = None   # serialized WorkflowState
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "UserState": ...
    @classmethod
    def fresh(cls) -> "UserState": ...   # default checklist, empty profile/history
```

Default checklist (3 items):
```python
[
    {"service_id": "cps_energy",     "name": "CPS Energy electric & gas",   "status": "pending", "lead_time_days": 2, "form_id": "cps_energy_start"},
    {"service_id": "saws",           "name": "SAWS water & sewer",          "status": "pending", "lead_time_days": 5, "form_id": "saws_start"},
    {"service_id": "cosa_solid_waste","name": "Trash, recycling & organics","status": "pending", "lead_time_days": 0, "form_id": "cosa_solid_waste"},
]
```

```python
class ChecklistTracker:
    def __init__(self, path: Path = USER_STATE_PATH): ...
    def _load(self) -> UserState: ...        # load from JSON or fresh()
    def save(self) -> None: ...
    def reset(self) -> None: ...            # state = fresh(), save()
    def get_item(self, service_id: str) -> ChecklistItem | None: ...
    def set_status(self, service_id: str, status: str, notes: str = "") -> None: ...
    def render_checklist(self) -> str: ...  # Markdown with [ ]/[~]/[x]/[-] symbols
    def update_profile(self, profile: dict) -> None: ...
    def set_active_workflow(self, workflow_state: dict | None) -> None: ...
    def append_history(self, role: str, content: str) -> None: ...
    # History capped at 200 entries. Each entry: {role, content, ts (UTC ISO)}
```

`render_checklist()` output format:
```
### Move-in checklist

[ ] **CPS Energy electric & gas** (pending)
[~] **SAWS water & sewer** (in_progress)
[x] **Trash, recycling & organics** (completed) - completed 2025-01-15T10:30:00
    _note text_
```

---

## 9. Agent Layer

### 9.1 `src/agent/prompts.py`

**`SYSTEM_PROMPT`** instructs the model to:
- Answer questions about CPS Energy, SAWS, and City of SA by calling `retrieve_knowledge` — never use training data for factual claims
- Only call `start_form_workflow` when the user explicitly asks to sign up/start/enroll — not for greetings, small talk, or "how do I" questions
- If intent is ambiguous, ask in plain text instead of calling the tool
- End every factual claim with an inline citation `(Source, Title)` using exact strings from `retrieve_knowledge` results
- Use `source_filter` when user names a specific provider
- Never request SSN/DL outside a form workflow
- Disclose that forms do not actually submit to providers

**`TOOL_DEFINITIONS`** — 5 tools:
1. `retrieve_knowledge(query, k=5, source_filter=[...])` — search knowledge base
2. `show_checklist()` — display checklist (no params)
3. `start_form_workflow(service_id)` — begin signup workflow; `service_id` ∈ `{cps_energy, saws, cosa_solid_waste}`
4. `mark_service_status(service_id, status, notes="")` — update checklist item
5. `update_profile(field, value)` — save a profile fact for pre-filling

**`build_grounding_block(passages)`** — formats retrieved passages as a tool-result string. Each passage rendered as:
```
[N] source='X' title='Y'
    url: URL
    text: TEXT
```
Returns a "no matching passages" message if the list is empty.

### 9.2 `src/agent/llm_client.py`

```python
class LLMClient:
    def __init__(self, model, base_url, api_key, demo_mode): ...
    def chat(self, messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2) -> dict:
        # Returns {"content": str, "tool_calls": list[dict]}
        # tool_calls items: {"id": str, "name": str, "arguments": dict}
```

Handles two tool-call response shapes from OpenAI-compatible servers:
1. Native `tool_calls` field on the response message
2. Inline JSON in the content field (some servers do this instead)

Inline extraction uses brace-matching (not regex) to handle nested braces. Detected by presence of `"name"`, `"function"`, `"parameters"`, or `"arguments"` substrings. Multiple calls per message supported. After extraction, the JSON is stripped from visible content.

**Demo mode** (no API key): first turn returns a `retrieve_knowledge` tool call with the user's message as query. Second turn (after tool result lands) returns a plain-text summary of the retrieved passages. Prefixes output with `_(demo mode - rule-based summary of retrieval results)_`.

### 9.3 `src/agent/tools.py`

```python
class ToolBox:
    def __init__(self, retriever: HybridRetriever, tracker: ChecklistTracker): ...
    def call(self, name: str, arguments: dict) -> dict:
        # Dispatches to _tool_{name}(**arguments)
        # Returns {"content": str, ...optional structured fields...}
```

Return dict optional fields used by orchestrator:
- `checklist_changed: True` — tells UI to refresh sidebar
- `start_workflow: "service_id"` — tells orchestrator to begin workflow (does NOT start it directly; orchestrator handles it)

Tool implementations:
- `_tool_retrieve_knowledge(query, k=5, source_filter=None)` → calls `retriever.search()`, formats with `build_grounding_block()`
- `_tool_show_checklist()` → `tracker.render_checklist()`
- `_tool_mark_service_status(service_id, status, notes="")` → `tracker.set_status()`; validates status is in allowed set
- `_tool_start_form_workflow(service_id)` → returns `{"content": "Starting...", "start_workflow": service_id}` — actual workflow object is created by orchestrator
- `_tool_update_profile(field, value)` → writes to `tracker.state.profile["user"][field]`

### 9.4 `src/agent/orchestrator.py`

```python
@dataclass
class AgentReply:
    text: str
    checklist_changed: bool = False

class AlamoAgent:
    MAX_TOOL_HOPS = 4  # module-level constant

    def __init__(self, retriever=None, tracker=None, llm=None):
        # Creates HybridRetriever (loads index), ChecklistTracker, LLMClient, ToolBox
        # Loads form schemas
        # Restores in-progress workflow from persisted state if any
```

**`handle_user_message(user_text: str) -> AgentReply`** — routing priority order:

1. **Pending-workflow confirmation**: if `_pending_workflow` is set, check if text matches `("yes", "y", "yeah", "yep", "sure", "ok", "okay", "begin", "start", "go")`. Input is normalized before matching: strip all non-alphabetic characters and lowercase. This means `Yes!`, `YES`, `YeS!?!` all match `yes`. If yes → `_commit_pending_workflow()`. Anything else → clear `_pending_workflow`, fall through.

2. **Checklist display shortcut**: if text matches `("show checklist", "show my checklist", "checklist")` → return `tracker.render_checklist()` directly, never route through LLM.

3. **Resume paused workflow**: if `workflow is None` and `_looks_like_resume(text)` (starts with "resume", "continue", "pick up", or "go back") and `tracker.state.active_workflow` is set → restore workflow from state, return resume message.

4. **Active form workflow** (not complete): route to `_handle_workflow_input(text)`.

5. **Completed form summary**: route to `_handle_workflow_summary(text)`, return result if not None, else fall through to LLM.

6. **LLM turn**: route to `_llm_turn(text)`.

All paths append to history via `tracker.append_history()`.

**`_looks_off_topic(text)`** — heuristic used during active workflow:
- Empty string → False
- In `("pause", "wait", "hold on", "stop")` → True
- Ends with `?` → True
- Matches any greeting in `_GREETINGS` (exact match or starts with greeting + space/comma) → True
- Starts with any prefix in `_COMMAND_PREFIXES` → True
- Otherwise → False

`_GREETINGS`: `("hi", "hello", "hey", "yo", "howdy", "good morning", "good afternoon", "good evening", "how are you", "how's it going", "what's up", "whats up", "thanks", "thank you", "ok", "okay")`

`_COMMAND_PREFIXES`: `("show ", "what ", "what'", "how ", "tell me", "explain", "help", "resume ", "cancel ", "start ", "sign me")`

**`_handle_workflow_input(text)`** — during active field entry:
- `"keep all"` → `workflow.keep_all()`, persist state
- `"undo"` / `"go back"` / `"back"` → `workflow.undo()`, persist state
- `"show checklist"` / `"show my checklist"` / `"checklist"` → render checklist + mid-signup note
- `"cancel"` / `"abort"` / `"quit form"` / `"quit"` → clear workflow and active_workflow, return cancellation message
- `"pause"` / `"wait"` / `"hold on"` / `"stop"` → set `self.workflow = None` (detach without clearing persisted state), return pause message with resume instructions
- `_looks_off_topic(text)` → return "We're mid-signup for **{title}**. Reply `pause` to step away and ask questions (progress is saved), or `cancel` to quit the form entirely."
- Otherwise → `workflow.submit_value(text)`, persist state

**`_handle_workflow_summary(text)`** — during completed summary:
- `"undo"` / `"back"` / `"go back"` → `workflow.edit_field(last_field.name)`, set `completed=False`, persist, return "Went back. {prompt}"
- `"submit"` → `workflow.commit(profile)`, `tracker.update_profile()`, `set_status(sid, "completed")`, clear active_workflow, clear `self.workflow`, return completion message with disclaimer
- `"edit {field_name}"` → `workflow.edit_field(field_name)`, return prompt
- `"cancel"` / `"abort"` → clear workflow + active_workflow, return "Cancelled."
- `None` → fall through to LLM

**`_llm_turn(text)`** — LLM agentic loop:
- Builds messages: system prompt → profile+checklist snapshot → last 12 history turns → current user text
- Loops up to `MAX_TOOL_HOPS = 4` times:
  - Call `llm.chat(messages, tools=TOOL_DEFINITIONS)`
  - If no tool calls: return content (or fallback string if empty)
  - Append assistant tool-request message and tool result messages to conversation
  - For each tool call: execute via `toolbox.call()`, check `start_workflow` signal
  - If `start_workflow` set: call `_begin_workflow(sid)`, return immediately
- If loop exhausted: return "I tried a few tool calls but couldn't reach a final answer."

**`_begin_workflow(service_id)`** — stages a workflow (does not start it):
- Stores `service_id` in `self._pending_workflow`
- Returns confirmation message asking user to reply `yes` to begin, explaining it's a {N}-field guided flow

**`_commit_pending_workflow()`** — actually starts the staged workflow:
- Creates `FormWorkflow(schema)`, calls `workflow.start(profile)`
- Calls `tracker.set_active_workflow()` and `tracker.set_status(sid, "in_progress")`
- Returns opener text

**`_restore_workflow_if_any()`** — called in `__init__`:
- If `tracker.state.active_workflow` is set, reconstructs `FormWorkflow` from persisted `WorkflowState`
- Sets `self.workflow` if found

**Message construction for LLM** (`_build_messages`):
```python
[
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "system", "content": "Current user profile (may be partial):\n{profile}\n\nCurrent checklist:\n{checklist}"},
    # last 12 turns from history (role: user or assistant only)
    {"role": "user", "content": current_user_text},
]
```

---

## 10. Gradio UI (`src/ui/gradio_app.py`)

### Constants

```python
MAX_CMDS = 16   # max simultaneous command buttons

COMMAND_LABELS: dict[str, str] = {
    "yes":                    "Yes",
    "no":                     "No",
    "keep":                   "Keep pre-filled value",
    "keep all":               "Keep all remaining pre-filled values",
    "skip":                   "Skip this field (optional)",
    "undo":                   "Undo last answer",
    "pause":                  "Pause form to ask a question",
    "cancel":                 "Cancel & discard current form",
    "submit":                 "Submit form",
    "show my checklist":      "Show my checklist",
    "start cps_energy":       "Start CPS Energy signup",
    "start saws":             "Start SAWS signup",
    "start cosa_solid_waste": "Start City of SA trash signup",
}
```

`WELCOME` — welcome message shown after model loads  
`LOADING_MSG` — shown immediately on page load while model downloads

### `build_app() -> gr.Blocks`

The agent is initialized lazily (set to `None` at closure scope, assigned in `_on_load()` via `nonlocal`). All inner functions guard with `if agent is None`.

**`_label_for(cmd: str) -> str`** (inside `build_app`, closes over `agent`):
- For `"start {sid}"` commands: looks up `agent.tracker.get_item(sid).status`; if `"completed"` or `"skipped"`, replaces `"Start "` with `"Restart "` in the base label
- For other commands: looks up `COMMAND_LABELS`
- For `"edit {name}"` commands: returns `"Edit: {name with spaces}"`
- For `"resume {sid}"` commands: returns `"Resume {sid with spaces}"`
- Fallback: returns command string as-is

**`_get_available_commands() -> list[str]`** (inside `build_app`, closes over `agent`):

| Agent state | Commands returned |
|---|---|
| `agent is None` | `[]` |
| `agent._pending_workflow` is set | `["yes", "no"]` |
| `agent.workflow` not None, not complete | context-sensitive (see below) |
| `agent.workflow` not None, complete (summary) | `["submit", "edit {field.name}" × all fields, "cancel"]` |
| no workflow, `tracker.state.active_workflow` has `service_id` | `[f"resume {sid}", "cancel"]` |
| idle | `["start cps_energy", "start saws", "start cosa_solid_waste", "show my checklist"]` |

During active field entry, commands are assembled in this order:
1. `"keep"` — only if `workflow.state.values.get(current_field.name) is not None`
2. `"skip"` — only if `not current_field.required`
3. `"keep all"` — only if any field at or after `current_field_index` has a non-empty value
4. `"undo"` — only if `current_field_index > 0`
5. `"pause"`, `"cancel"` — always

**`_compute_button_updates() -> list`**:
Returns `MAX_CMDS` `gr.update()` calls. Slots 0..len(cmds)-1 get `value=_label_for(cmds[i]), visible=True`. Slots len(cmds)..MAX_CMDS-1 get `value="", visible=False`.

### Layout

```
gr.Blocks(title="AlamoOnboard")
  gr.Markdown("# 🏛️ AlamoOnboard\n*San Antonio utilities & city-services concierge*")
  gr.Row()
    gr.Column(scale=3)                    # Left: chat
      gr.Chatbot(value=[LOADING_MSG], height=520)
      gr.Row()
        gr.Textbox(placeholder="Loading model — please wait...", scale=8,
                   show_label=False, container=False, interactive=False)
        gr.Button("Send", scale=1, variant="primary", interactive=False)
        gr.Button("Reset", scale=1, interactive=False)
    gr.Column(scale=2)                    # Right: status + commands
      gr.Markdown("### Status")
      gr.Markdown(value="_Loading..._")   # checklist_md
      gr.Markdown("---\n### Available Commands")
      [gr.Button("", visible=False, size="sm") for _ in range(16)]
      gr.Markdown("_Click to paste into chat, then press Enter._")
      gr.Markdown("_The checklist is persisted to `output/user_state.json`. ...")
```

Chatbot uses messages format (list of `{"role": ..., "content": ...}` dicts).

### Event wiring

**`app.load(_on_load)`** — fires when page loads:
- `nonlocal agent; agent = AlamoAgent()`
- `agent.retriever.embedder.encode(["warmup"])` — forces lazy model download NOW
- Returns: `[chatbot(WELCOME), checklist_md, msg(interactive=True), send(interactive=True), clear(interactive=True), *cmd_btns]`
- 18 total outputs: `[chatbot, checklist_md, msg, send, clear, btn0, ..., btn15]`

**`send.click` / `msg.submit`** → `_send(user_message, history)`:
- Calls `respond(user_message, history)`
- Returns: `("", new_history, new_checklist, *_compute_button_updates())`
- 19 outputs: `[msg, chatbot, checklist_md, btn0..btn15]`

**`clear.click`** → `reset_state()`:
- If agent is None: return loading state with all buttons hidden
- Otherwise: `agent.tracker.reset()`, `agent.workflow = None`, `agent._pending_workflow = None` # tracker.reset() calls UserState.fresh() which clears profile, checklist, active_workflow, and history
- Returns: `([WELCOME msg], checklist, *_compute_button_updates())`
- Outputs: `[chatbot, checklist_md, btn0..btn15]`

**Button click handlers** (one per button, using closure to capture index):
```python
for i in range(MAX_CMDS):
    def make_handler(idx):
        def handler():
            cmds = _get_available_commands()
            return cmds[idx] if idx < len(cmds) else ""
        return handler
    cmd_btns[i].click(fn=make_handler(i), inputs=[], outputs=[msg])
```
Clicking a button pastes the raw command string (not the label) into the text input. The user then presses Enter to send.

**`respond(user_message, history)`**:
```python
def respond(user_message, history):
    history = history or []
    if not user_message or agent is None:
        return history, ""
    history.append({"role": "user", "content": user_message})
    reply = agent.handle_user_message(user_message)
    history.append({"role": "assistant", "content": reply.text})
    return history, agent.tracker.render_checklist()
```

### Launch

```python
app.launch(
    server_name="127.0.0.1",
    server_port=7860,
    inbrowser=True,
    theme=gr.themes.Soft(),
)
```

---

## 11. Persistence Format (`output/user_state.json`)

```json
{
  "profile": {
    "user": {
      "first_name": "...",
      "last_name": "...",
      "email": "...",
      "phone": "...",
      "service_address": "...",
      "service_city": "...",
      "service_zip": "..."
    }
  },
  "checklist": [
    {
      "service_id": "cps_energy",
      "name": "CPS Energy electric & gas",
      "status": "pending",
      "lead_time_days": 2,
      "form_id": "cps_energy_start",
      "completed_at": null,
      "notes": ""
    }
  ],
  "active_workflow": {
    "service_id": "cps_energy",
    "current_field_index": 3,
    "values": {"first_name": "...", "last_name": "..."},
    "completed": false,
    "errors": {}
  },
  "history": [
    {"role": "user", "content": "...", "ts": "2025-01-15T10:00:00"},
    {"role": "assistant", "content": "...", "ts": "2025-01-15T10:00:01"}
  ]
}
```

`active_workflow` is `null` when no form is in progress.  
History is capped at 200 entries (last 200 kept).

---

## 12. Key Behaviors Summary

1. **Lazy model loading**: `Embedder._model` is `None` until first `.encode()`. The Gradio `app.load()` handler triggers it via `encode(["warmup"])` so the loading message is visible during the download.

2. **Form workflow confirmation gate**: `start_form_workflow` tool call from LLM only *stages* the workflow (stores `service_id` in `_pending_workflow`). The user must explicitly reply `yes` (or equivalent) before the workflow actually starts. Any other reply discards the staged workflow.

3. **Workflow persistence**: `WorkflowState.to_dict()` is called after every field answer and stored in `user_state.json` via `tracker.set_active_workflow()`. On restart, `AlamoAgent.__init__` restores it via `_restore_workflow_if_any()`.

4. **Checklist display shortcut**: `"show my checklist"` / `"show checklist"` / `"checklist"` are intercepted in `handle_user_message()` before any other routing — including mid-workflow. This prevents them from being treated as field values or routed through the LLM.

5. **Off-topic detection**: during active form field entry, `_looks_off_topic()` catches questions, greetings, and agent-directed commands and responds with a pause/cancel prompt instead of treating the text as a field value.

6. **Soft pause vs. hard cancel**: `"pause"` sets `self.workflow = None` but leaves `tracker.state.active_workflow` intact, so the user can resume. `"cancel"` clears both. A cancel arriving while in the paused state (i.e. `self.workflow is None` but `active_workflow` is set) is caught in `handle_user_message()` before routing to the LLM — it clears `active_workflow` and returns a confirmation message, returning the user to idle.

7. **Keep all**: advances through consecutive pre-filled fields in index order, stopping at the first field with no value. Returns next prompt or summary.

8. **Undo**: steps back one field, clears its stored value and error, resets `completed=False` if on summary. Guard at index 0.

9. **Start/Restart labels**: `_label_for()` queries `agent.tracker.get_item(sid).status`; if `"completed"` or `"skipped"`, replaces `"Start "` with `"Restart "` in the button label. The raw command string pasted into the chat is unchanged.

10. **Demo mode**: when no LLM API key is configured, `LLMClient` uses a two-turn rule-based stub: first turn requests `retrieve_knowledge`, second turn summarizes the results in plain text. Full form workflow and checklist features still work.

11. **Inline tool call extraction**: some OpenAI-compatible servers embed tool calls as JSON in the content field rather than using the structured `tool_calls` field. `LLMClient` detects and normalizes this case.

12. **Source filtering**: `retrieve_knowledge` accepts an optional `source_filter` list. Only chunks whose `source` matches one of the display names (`"CPS Energy"`, `"SAWS"`, `"City of San Antonio"`) are returned.

13. **Citation policy**: every factual claim in LLM responses must cite `(Source, Title)` using exact strings from retrieval results.

---

## 13. Build / Rebuild Flow

1. Run SA Utilities pipeline (sibling package) to produce `all_chunks.json` and ChromaDB:
   ```
   python -m sa_utilities.pipeline.runner
   python -m sa_utilities.pipeline.embedder
   ```

2. Build the FAISS index (happens automatically on first `python main.py`, or explicitly):
   ```
   python main.py --rebuild
   ```
   This calls `HybridRetriever.build_from_sa_utilities()`:
   - Reads chunks from `all_chunks.json`
   - Fetches embeddings from ChromaDB by `chunk_id`
   - L2-normalizes vectors
   - Builds `faiss.IndexFlatIP`, saves to `output/index/`
   - Initializes `BM25Okapi` from chunk texts

3. Run the application:
   ```
   python main.py          # Gradio UI at http://127.0.0.1:7860
   python main.py --cli    # Text REPL
   ```

---

## 14. `src/utils/logging_utils.py`

Simple wrapper returning a Python `logging.Logger` for a given name. Should configure a handler that writes to `output/logs/` and to stdout.

---

## 15. All `__init__.py` Files

All `__init__.py` files in `src/`, `src/agent/`, `src/checklist/`, `src/forms/`, `src/indexer/`, `src/ui/`, `src/utils/` are empty (or contain only `from __future__ import annotations`). They exist only to make the directories importable as packages.
