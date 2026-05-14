# AlamoOnboard — System Specification

**Project:** CS 6263 NLP and Agentic AI — Final Project  
**Version:** 1.0.0  
**Model for regeneration:** `claude-opus-4-5-20251101`, temperature 0

**Architecture diagram:** `docs/diagrams/architecture.svg` (source: `docs/diagrams/architecture_source.md`)

---

## Purpose

AlamoOnboard is a conversational AI concierge that helps people relocating to San Antonio, Texas set up their essential utilities and city services. New residents must independently navigate three separate providers — CPS Energy (electric and gas), the San Antonio Water System (water and sewer), and the City of San Antonio Solid Waste Management (trash, recycling, and organics) — each with its own website, form, lead-time requirements, and deposit rules. AlamoOnboard unifies all three into a single chat interface backed by a retrieval-augmented knowledge base and a step-by-step guided form system.

The system serves a user who has just signed a lease or closed on a home in San Antonio and needs to activate utility accounts before their move-in date. It answers factual questions about rates, deposits, and policies by retrieving information scraped from the providers' official websites; it tracks the user's progress on a persistent move-in checklist; and it walks the user field-by-field through each provider's signup form, pre-filling known values from previous forms and validating each answer before moving on. All form data is collected locally and is not transmitted to any provider — the system is a guided data-collection prototype, not a live integration.

---

## Component Inventory

### Main Application (`src/`)

| Component | Module Path | Responsibility |
|---|---|---|
| Entry point | `main.py` | CLI argument parsing; index build or load; launches UI or REPL |
| Configuration | `config.py` | All env-var resolution and path constants |
| Gradio UI | `src/ui/gradio_app.py` | Blocks layout, lazy agent init, dynamic command buttons, event wiring |
| Agent orchestrator | `src/agent/orchestrator.py` | Top-level message router; form FSM lifecycle; LLM agentic loop |
| LLM client | `src/agent/llm_client.py` | OpenAI-compatible chat completions; demo stub; inline tool-call extraction |
| Prompts | `src/agent/prompts.py` | SYSTEM_PROMPT, TOOL_DEFINITIONS, grounding block formatter |
| Tool box | `src/agent/tools.py` | Executes tool calls: retrieve, checklist ops, workflow trigger, profile update |
| Checklist tracker | `src/checklist/tracker.py` | UserState / ChecklistItem persistence; checklist rendering |
| Form schemas | `src/forms/schemas.py` | FormSchema / FormField dataclasses; JSON loader |
| Form workflow | `src/forms/workflow.py` | FormWorkflow FSM; WorkflowState; field-by-field guidance |
| Form validators | `src/forms/validators.py` | Validator registry: email, phone, ZIP, address, SSN, dates, lead times |
| Pre-fill logic | `src/forms/prefill.py` | Cross-form profile pre-fill; profile update from completed form |
| Embedder | `src/indexer/embedder.py` | Lazy sentence-transformers wrapper |
| Vector store | `src/indexer/vector_store.py` | FAISS IndexFlatIP with JSON metadata sidecar |
| Loaders | `src/indexer/loaders.py` | SA Utilities → FAISS adapter; ChromaDB embedding fetch |
| Retriever | `src/indexer/retriever.py` | HybridRetriever: BM25 + FAISS + Reciprocal Rank Fusion |
| Logging utils | `src/utils/logging_utils.py` | JSON-structured logging; request_id propagation via contextvars |

### SA Utilities Pipeline (`sa_utilities/`)

| Component | Module Path | Responsibility |
|---|---|---|
| SA Utilities config | `sa_utilities/config.py` | Paths, crawl delay, embedding batch size, chunk config |
| Data models | `sa_utilities/models.py` | SourceDocument, Chunk dataclasses; DocType and Source enums |
| Pipeline runner | `sa_utilities/pipeline/runner.py` | Orchestrates fetch → chunk → save; merges incremental runs |
| Chunker | `sa_utilities/pipeline/chunker.py` | Splits SourceDocuments into overlap-aware Chunks |
| Embedder | `sa_utilities/pipeline/embedder.py` | Encodes chunks with SentenceTransformer; upserts to ChromaDB |
| Fingerprinter | `sa_utilities/pipeline/fingerprinter.py` | ETag/Last-Modified/content-hash change detection; idempotent runs |
| CPS Energy adapter | `sa_utilities/adapters/cps.py` | Scrapes CPS Energy rate PDFs and HTML policy pages |
| SAWS adapter | `sa_utilities/adapters/saws.py` | Scrapes SAWS HTML tables, rates, signup pages |
| CoSA adapter | `sa_utilities/adapters/cosa.py` | Scrapes City of SA solid waste and library pages |

### Static Data

| Artifact | Path | Description |
|---|---|---|
| Form schemas | `data/form_schemas.json` | JSON definitions for all three service signup forms |
| Raw scrape output | `sa_utilities/data/raw/` | Per-source JSON files from the fetch phase |
| Chunk metadata | `sa_utilities/data/chunks/all_chunks.json` | All chunk metadata (no embeddings) from the chunk phase |
| ChromaDB | `sa_utilities/data/chroma/` | Persistent ChromaDB holding chunk embeddings, keyed by chunk_id |
| FAISS index | `output/index/index.faiss` | Inner-product FAISS index (built from ChromaDB at first run) |
| FAISS metadata | `output/index/meta.json` | Chunk metadata parallel to FAISS rows |
| User state | `output/user_state.json` | Persisted checklist, profile, active workflow, and history |

---

## Data Flow

### Runtime Query Flow

```
User types message in Gradio chat
        │
        ▼
src/ui/gradio_app.py  ─── respond() ──►  AlamoAgent.handle_user_message()
                                                    │
                          ┌─────────────────────────┼──────────────────────────┐
                          ▼                         ▼                          ▼
               Checklist shortcut        Active FormWorkflow FSM         _llm_turn()
               (deterministic,           (field-by-field guidance,            │
               never hits LLM)           validators, keep/skip/undo)          │
                          │                         │                          ▼
                          │                         │               LLMClient.chat()
                          │                         │               (OpenAI-compatible
                          │                         │                endpoint or demo stub)
                          │                         │                          │
                          │                         │               ┌──────────┴──────────┐
                          │                         │               ▼                     ▼
                          │                         │         tool_calls             plain text
                          │                         │               │                     │
                          │                         │               ▼                     │
                          │                         │         ToolBox.call()              │
                          │                         │         ┌────┴────────────┐         │
                          │                         │         ▼                 ▼         │
                          │                         │  retrieve_knowledge  start_form     │
                          │                         │         │            mark_status    │
                          │                         │         ▼            update_profile │
                          │                         │  HybridRetriever.search()           │
                          │                         │  ┌──────┴──────┐                   │
                          │                         │  ▼             ▼                   │
                          │                         │ FAISS dense   BM25 keyword         │
                          │                         │  └──────┬──────┘                   │
                          │                         │         ▼                           │
                          │                         │  Reciprocal Rank Fusion             │
                          │                         │  → list[RetrievedPassage]           │
                          │                         │         │                           │
                          └─────────────────────────┴─────────┴───────────────────────────┘
                                                             │
                                                             ▼
                                                   AgentReply.text
                                                             │
                                                             ▼
                                           Gradio chatbot + checklist sidebar updated
                                           User state saved to output/user_state.json
```

### SA Utilities Pipeline Data Flow (run once before main app)

```
CPS Energy website / PDFs
SAWS website / HTML tables         ──► sa_utilities/adapters/*.py
City of SA website                         (fetch, extract, normalize)
                                                    │
                                                    ▼
                                           list[SourceDocument]
                                           saved to sa_utilities/data/raw/
                                                    │
                                                    ▼
                                    sa_utilities/pipeline/chunker.py
                                    (split with overlap, prepend title)
                                                    │
                                                    ▼
                                           list[Chunk]
                                           saved to sa_utilities/data/chunks/all_chunks.json
                                                    │
                                                    ▼
                                    sa_utilities/pipeline/embedder.py
                                    (SentenceTransformer all-MiniLM-L6-v2, batch 64)
                                                    │
                                                    ▼
                                    ChromaDB at sa_utilities/data/chroma/
                                    (collection: sa_utilities, keyed by chunk_id)
                                                    │
                                                    ▼ (main app first run)
                                    src/indexer/loaders.py
                                    (fetch embeddings from ChromaDB, L2-normalize)
                                                    │
                                                    ▼
                                    src/indexer/vector_store.py
                                    (build FAISS IndexFlatIP, save index.faiss + meta.json)
                                                    │
                                                    ▼
                                    output/index/ (used for all subsequent runtime searches)
```

### User State Persistence

Every agent turn that changes state writes `output/user_state.json` atomically:
- `profile.user.*` — updated when `update_profile` tool is called or a form is submitted
- `checklist[*].status` — updated at workflow start (`in_progress`) and submit (`completed`)
- `active_workflow` — serialized `WorkflowState` dict; `null` when no form is in progress
- `history` — last 200 turns appended each response; used as short-term memory for LLM context

---

## Public Interfaces

### `main.py`

```python
def main() -> None:
    # Parses --rebuild and --cli flags.
    # Always calls cmd_build_index(rebuild) first.
    # Launches cmd_run_ui() or cmd_run_cli().

def cmd_build_index(rebuild: bool) -> None:
    # Loads existing FAISS index from output/index/.
    # If load fails or rebuild=True, calls retriever.build_from_sa_utilities().

def cmd_run_ui() -> None:
    # Imports and calls src.ui.gradio_app.main()

def cmd_run_cli() -> None:
    # Text REPL: creates AlamoAgent, loops input() → agent.handle_user_message() → print
```

### `src/agent/orchestrator.py`

```python
@dataclass
class AgentReply:
    text: str
    checklist_changed: bool = False

class AlamoAgent:
    retriever: HybridRetriever
    tracker: ChecklistTracker
    llm: LLMClient
    toolbox: ToolBox
    schemas: dict[str, FormSchema]
    workflow: FormWorkflow | None
    _pending_workflow: str | None

    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        tracker: ChecklistTracker | None = None,
        llm: LLMClient | None = None,
    ) -> None: ...

    def handle_user_message(self, user_text: str) -> AgentReply:
        # Primary entry point. Routing priority:
        # 1. Pending-workflow confirmation — input is normalized before matching:
        #    strip leading/trailing whitespace, strip surrounding punctuation,
        #    convert to lowercase. "yes", "Yes", "YES", "yes!", "YeS!?!" all confirm.
        #    Any non-yes input exits the pending state and returns to idle chat.
        # 2. Checklist display shortcut
        # 3. Resume paused workflow
        # 4. Active form field entry
        # 5. Completed form summary
        # 6. LLM turn with tools
```

### `src/agent/llm_client.py`

```python
class LLMClient:
    def __init__(
        self,
        model: str = LLM_MODEL,
        base_url: str | None = LLM_BASE_URL,
        api_key: str | None = LLM_API_KEY,
        demo_mode: bool = DEMO_MODE,
    ) -> None: ...

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
    ) -> dict:
        # Returns {"content": str, "tool_calls": list[{"id", "name", "arguments"}]}
        # Falls back to _demo_chat() when demo_mode=True or no API key.
```

### `src/agent/tools.py`

```python
class ToolBox:
    def __init__(self, retriever: HybridRetriever, tracker: ChecklistTracker) -> None: ...

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        # Dispatches to _tool_{name}(**arguments).
        # Return dict always has "content" key.
        # Optional keys: "checklist_changed": bool, "start_workflow": str

    # Tool implementations (called via dispatch):
    def _tool_retrieve_knowledge(self, query: str, k: int = 5, source_filter: list[str] | None = None) -> dict
    def _tool_show_checklist(self) -> dict
    def _tool_mark_service_status(self, service_id: str, status: str, notes: str = "") -> dict
    def _tool_start_form_workflow(self, service_id: str) -> dict
    def _tool_update_profile(self, field: str, value: str) -> dict
```

### `src/agent/prompts.py`

```python
SYSTEM_PROMPT: str  # Full LLM system prompt (see Model and Prompt Selection section)

TOOL_DEFINITIONS: list[dict]  # OpenAI tool schema for all 5 tools

def build_grounding_block(passages: list[RetrievedPassage]) -> str:
    # Formats retrieved passages as tool-result string with source/title for citations.
    # Returns "no matching passages" string if list is empty.
```

### `src/checklist/tracker.py`

```python
@dataclass
class ChecklistItem:
    service_id: str
    name: str
    status: str          # "pending" | "in_progress" | "completed" | "skipped"
    lead_time_days: int
    form_id: str
    completed_at: str | None
    notes: str

@dataclass
class UserState:
    profile: dict[str, Any]
    checklist: list[ChecklistItem]
    active_workflow: dict | None    # serialized WorkflowState, or None
    history: list[dict]             # {"role", "content", "ts"} per turn

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "UserState": ...
    @classmethod
    def fresh(cls) -> "UserState": ...  # default checklist, empty profile

class ChecklistTracker:
    state: UserState
    path: Path

    def __init__(self, path: Path = USER_STATE_PATH) -> None: ...
    def save(self) -> None: ...
    def reset(self) -> None: ...
        # Resets to UserState.fresh(): clears profile, checklist, active workflow,
        # and full conversation history. After reset, no prior state or error
        # messages remain.
    def get_item(self, service_id: str) -> ChecklistItem | None: ...
    def set_status(self, service_id: str, status: str, notes: str = "") -> None: ...
    def render_checklist(self) -> str: ...   # Markdown with [ ]/[~]/[x]/[-] symbols
    def update_profile(self, profile: dict) -> None: ...
    def set_active_workflow(self, workflow_state: dict | None) -> None: ...
    def append_history(self, role: str, content: str) -> None: ...
    # History capped at 200 entries
```

### `src/forms/schemas.py`

```python
@dataclass
class FormField:
    name: str
    label: str
    type: str            # "text"|"email"|"phone"|"address"|"date"|"select"|"boolean"|"secret"
    required: bool
    validator: str | None
    prefill_from: str | None   # dotted path e.g. "user.first_name"
    default: Any
    options: list[str]
    help: str

@dataclass
class FormSchema:
    service_id: str
    title: str
    provider: str
    submit_url: str
    lead_time_days: int
    description: str
    fields: list[FormField]
    completion_message: str

    @classmethod
    def from_dict(cls, d: dict) -> "FormSchema": ...

def load_schemas(path: Path = FORM_SCHEMAS_PATH) -> dict[str, FormSchema]:
    # Keyed by service_id: "cps_energy", "saws", "cosa_solid_waste"
```

### `src/forms/workflow.py`

```python
@dataclass
class WorkflowState:
    service_id: str
    current_field_index: int
    values: dict[str, Any]
    completed: bool
    errors: dict[str, str]

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowState": ...

class FormWorkflow:
    schema: FormSchema
    state: WorkflowState

    def __init__(self, schema: FormSchema, state: WorkflowState | None = None) -> None: ...
    def start(self, profile: dict) -> str: ...          # pre-fill + return intro message
    def is_complete(self) -> bool: ...
    @property
    def current_field(self) -> FormField | None: ...
    def prompt_for_current_field(self) -> str: ...
    def submit_value(self, raw_value: str) -> tuple[bool, str]: ...  # (advanced, message)
    def keep_all(self) -> str: ...        # accept all consecutive pre-filled fields
    def undo(self) -> str: ...            # step back one field, clear its value
    def edit_field(self, field_name: str) -> str: ...   # jump to named field
    def commit(self, profile: dict) -> dict: ...        # write values back to profile
```

### `src/forms/validators.py`

```python
ValidationResult = tuple[bool, str, str]   # (ok, cleaned_value, error_message)

def validate(name: str, value: str) -> ValidationResult:
    # Looks up validator by name. Unknown names pass through unchanged.

# Individual validators (all same signature):
def email(value: str) -> ValidationResult: ...
def phone_us(value: str) -> ValidationResult: ...
def zip_us(value: str) -> ValidationResult: ...
def address(value: str) -> ValidationResult: ...
def ssn_or_dl(value: str) -> ValidationResult: ...
def ssn_last4(value: str) -> ValidationResult: ...
def cps_account(value: str) -> ValidationResult: ...
def lead_time_2bd(value: str) -> ValidationResult: ...   # ≥ 2 business days
def lead_time_5bd(value: str) -> ValidationResult: ...   # ≥ 5 business days
def date_field(value: str) -> ValidationResult: ...

VALIDATORS: dict[str, Callable]   # registry keyed by validator name string
```

### `src/forms/prefill.py`

```python
def prefill_form(schema: FormSchema, profile: dict) -> dict[str, Any]:
    # Resolves "user.X" dotted paths against profile.
    # Falls back to field.default if profile value missing.
    # Returns {field_name: value} for all fields with a resolved value.

def update_profile_from_form(profile: dict, schema: FormSchema, form_values: dict) -> dict:
    # Pushes non-secret form values to profile["user"][key].
    # Never writes fields with type="secret" to profile.
    # Returns updated profile dict.

def field_summary(field: FormField, value: Any) -> str:
    # Returns "  - Label: value" line for summary screen.
    # Masks secret fields: shows masked form or "***hidden***".
```

### `src/indexer/embedder.py`

```python
class Embedder:
    model_name: str
    _model: SentenceTransformer | None   # None until first encode()

    def __init__(self, model_name: str = EMBED_MODEL) -> None: ...

    @property
    def model(self) -> SentenceTransformer: ...   # loads lazily on first access

    @property
    def dim(self) -> int: ...

    def encode(self, texts: Iterable[str], normalize: bool = True) -> np.ndarray:
        # Returns (N, dim) float32 array. Empty input → (0, dim) zeros.
```

### `src/indexer/vector_store.py`

```python
class VectorStore:
    index_dir: Path
    index_path: Path      # output/index/index.faiss
    meta_path: Path       # output/index/meta.json

    def __init__(self, index_dir: Path = INDEX_DIR) -> None: ...
    def build(self, vectors: np.ndarray, metadata: Sequence[dict]) -> None: ...
    def save(self) -> None: ...
    def load(self) -> bool: ...   # returns False if files missing
    def search(self, query_vec: np.ndarray, k: int = 5) -> list[tuple[float, dict]]: ...
    def __len__(self) -> int: ...
```

### `src/indexer/retriever.py`

```python
@dataclass
class RetrievedPassage:
    text: str
    title: str
    source: str    # "CPS Energy" | "SAWS" | "City of San Antonio"
    url: str
    score: float

    def citation(self) -> str: ...

class HybridRetriever:
    embedder: Embedder
    store: VectorStore

    def __init__(self) -> None: ...
    def build_from_sa_utilities(self) -> None: ...
    def load(self) -> bool: ...

    def search(
        self,
        query: str,
        k: int = TOP_K,
        source_filter: Iterable[str] | None = None,
    ) -> list[RetrievedPassage]:
        # BM25 keyword + FAISS dense, fused by Reciprocal Rank Fusion (k=60).
        # source_filter restricts by display name (e.g. ["CPS Energy"]).
```

### `src/utils/logging_utils.py`

```python
_request_id_var: contextvars.ContextVar[str]  # module-level context variable

def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    # Configures root logger with JSON formatter once (idempotent).
    # Each log entry: {"timestamp", "level", "module", "request_id", "message"}
    # Quiets chatty third-party loggers (urllib3, httpx, sentence_transformers).

def get_logger(name: str) -> logging.Logger:
    # Returns named logger; triggers setup_logging on first call.

def set_request_id(request_id: str) -> None:
    # Sets the request_id for the current coroutine/thread context.
    # Call once at the top of handle_user_message(); all subsequent
    # log calls in that turn automatically include this ID.

def get_request_id() -> str:
    # Returns current request_id, or "-" if none is set.
```

### SA Utilities Pipeline — Public Interfaces

#### `sa_utilities/models.py`

```python
class DocType(str, Enum):
    RATE = "rate"; POLICY = "policy"; SIGNUP = "signup"; FEE = "fee"
    FAQ = "faq"; ASSISTANCE = "assistance"; GENERAL = "general"

class Source(str, Enum):
    CPS = "cps"; SAWS = "saws"; COSA = "cosa"

@dataclass
class SourceDocument:
    source: Source; doc_type: DocType; title: str; url: str; content: str
    effective_date: str | None; metadata: dict

    def char_count(self) -> int: ...

@dataclass
class Chunk:
    chunk_id: str; source: Source; doc_type: DocType; title: str
    url: str; text: str; chunk_index: int; embedding: list | None
```

#### `sa_utilities/pipeline/runner.py`

```python
def run(
    sources: list[str] | None = None,
    no_fetch: bool = False,
) -> tuple[list[SourceDocument], list[Chunk]]:
    # Runs fetch → chunk → save for the named sources (default: all three).
    # --no-fetch reloads from sa_utilities/data/raw/ without hitting the web.
    # Merges new chunks with existing all_chunks.json by URL deduplication.
    # Returns (all_docs, all_chunks).

# CLI: python -m sa_utilities.pipeline.runner [--sources cps saws cosa] [--no-fetch]
```

#### `sa_utilities/pipeline/embedder.py`

```python
def embed(
    sources: list[str] | None = None,
    force: bool = False,
) -> int:
    # Encodes chunks from all_chunks.json with SentenceTransformer.
    # Upserts to ChromaDB collection "sa_utilities".
    # Returns number of chunks upserted.
    # force=True re-embeds even unchanged chunks.

# CLI: python -m sa_utilities.pipeline.embedder [--sources ...] [--force]
```

#### `sa_utilities/pipeline/chunker.py`

```python
def chunk_documents(documents: list[SourceDocument]) -> list[Chunk]: ...
def chunk_document(doc: SourceDocument) -> list[Chunk]: ...
# Chunk sizes (chars): RATE/FEE=600, POLICY/ASSISTANCE=800, others=700
# Overlap: 100-150 chars depending on doc type
# Every chunk text is prefixed with the parent document title
```

#### `sa_utilities/pipeline/fingerprinter.py`

```python
class Fingerprinter:
    def check(self, url: str, response: requests.Response) -> CheckResult: ...
    def save(self) -> None: ...
    # Strategies in priority order: ETag > Last-Modified > content SHA256
    # Tracks last_fetched and last_changed per URL
```

#### Adapters (`sa_utilities/adapters/`)

All adapters share the same interface:

```python
class CPSAdapter:   # (same pattern for SAWSAdapter, CoSAAdapter)
    def fetch_all(self) -> list[SourceDocument]: ...
    # Fetches and normalizes all documents for this source.
    # Applies politeness delay (CRAWL_DELAY = 1.0s per request).
    # Returns list of SourceDocument with source, doc_type, title, url, content set.
```

---

## Model and Prompt Selection

### Embedding Model: `sentence-transformers/all-MiniLM-L6-v2`

**Why this model:**
- 384-dimensional embeddings fit comfortably in a FAISS IndexFlatIP without quantization
- 22M parameters — fast enough to encode at startup and for every query on CPU
- Strong performance on semantic similarity benchmarks relative to its size (MTEB leaderboard)
- Apache 2.0 license; available directly from HuggingFace Hub without API access

**Parameters:**
- Dimension: 384 (set via `ALAMO_EMBED_DIM`, default `384`)
- Normalization: L2-normalized before FAISS indexing so inner-product equals cosine similarity
- Batch size for offline embedding: 64 chunks (SA Utilities pipeline)
- The same model is used in both the SA Utilities pipeline (offline embedding) and the main app (query encoding at runtime) to guarantee embedding space alignment

**Retrieval architecture rationale (hybrid BM25 + FAISS):**
- Dense retrieval (FAISS) handles semantic queries: "how much do I owe upfront" → finds deposit information
- Sparse retrieval (BM25) handles keyword queries: "REAP", "210-353-2222" → exact term matches
- Reciprocal Rank Fusion (RRF, k=60) merges the two ranked lists without requiring score calibration between the two systems. RRF is chosen over score-level fusion because BM25 scores are unbounded and not comparable to cosine similarities.

### LLM: `llama-3.3-70b-instruct-awq` (configurable)

**Why this model (default):**
- Served on the course-provided OpenAI-compatible inference endpoint (`ALAMO_LLM_BASE_URL`)
- AWQ 4-bit quantized — fits on a single A100 while preserving instruction-following quality
- 70B parameter Llama 3.3 generation produces coherent multi-turn dialogue and respects tool-calling schemas
- The model name is fully configurable via `ALAMO_LLM_MODEL` — any OpenAI-compatible model can be substituted without code changes

**Demo mode fallback:**
- When `ALAMO_LLM_API_KEY` is not set, `DEMO_MODE=True` activates automatically
- The demo stub performs one `retrieve_knowledge` call per turn and summarizes the results in plain text
- All form workflows and checklist features continue to work in demo mode (they do not use the LLM)

**LLM temperature:** 0.2 (set in `LLMClient.chat()`; slightly above 0 to allow natural phrasing variation while keeping responses consistent)

### System Prompt

```
You are AlamoOnboard, a friendly assistant that helps people who are moving to San Antonio, Texas, set up their utilities and city services.

Capabilities:
- Answer questions about CPS Energy (electric & gas), SAWS (water & sewer), and the City of San Antonio (trash, recycling, 311, hazardous waste). Always ground factual claims in retrieve_knowledge results, never your training data.
- When and ONLY when the user explicitly asks to sign up, start, enroll, or fill out a form for one of those services, walk them through the signup with start_form_workflow.
- Track progress on a move-in checklist. Use show_checklist whenever the user asks "what's left" or "where am I".
- Pre-fill fields automatically from the user's profile when possible.

Tool routing rules (READ CAREFULLY):
- `start_form_workflow` is a hard commitment. Once you call it, the form module takes over and the user is locked into a 14-field guided signup until they submit or cancel. NEVER call it speculatively, NEVER call it just because a service was the topic of the previous message, and NEVER call it in response to greetings ("hi", "how are you", "thanks") or generic small talk. Only call it when the user has clearly and explicitly asked to begin the signup, with phrases like "sign me up for SAWS", "let's start the CPS Energy signup", "help me enroll", "fill out the SAWS form", or similar direct requests.
- For "tell me about X", "what does X cost", "how do I sign up for X" (asking how, not asking to do it), use `retrieve_knowledge`, not `start_form_workflow`.
- If you are unsure whether the user wants to start a workflow or just learn more, ASK them in plain text. Do not guess by calling the tool.
- For greetings and small talk, just respond conversationally in plain text. Do not call any tool.

Citation policy (REQUIRED):
- Every factual claim about deposits, rates, lead times, fees, phone numbers, or policies MUST end with an inline citation in the format (Source, Title). For example: "SAWS asks for about a $100 deposit (SAWS, New Service Deposit)."
- Use the exact source and title strings returned by retrieve_knowledge. Do not invent citations.
- If retrieve_knowledge returns nothing relevant, say so plainly. Do not fabricate facts to fill the gap.
- When the user explicitly names one provider ("for SAWS only", "just CPS Energy"), pass `source_filter` to retrieve_knowledge to restrict results.

Style:
- Be warm, concise, and specific. Default to short paragraphs and short numbered lists.
- Never invent rates, deadlines, or phone numbers.
- Do not request a Social Security Number, driver license, or other sensitive ID until the user is inside a form workflow that needs it.
- This is a teaching prototype. The forms collect data locally and do NOT actually submit to CPS Energy, SAWS, or the City of San Antonio. Be transparent about that when relevant.
```

### Tool Definitions

Five tools are exposed to the LLM via `TOOL_DEFINITIONS` in `src/agent/prompts.py`:

**`retrieve_knowledge`** — searches the FAISS+BM25 knowledge base
- `query: str` (required) — natural-language query
- `k: int` (optional, default 5) — number of passages to return
- `source_filter: list[str]` (optional) — restrict to `["CPS Energy"]`, `["SAWS"]`, `["City of San Antonio"]`, or any combination

**`show_checklist`** — renders the user's move-in checklist (no parameters)

**`start_form_workflow`** — signals intent to begin a signup form
- `service_id: str` (required) — one of `"cps_energy"`, `"saws"`, `"cosa_solid_waste"`
- Note: this tool only signals intent; the orchestrator requires explicit user confirmation before committing

**`mark_service_status`** — updates a checklist item
- `service_id: str` (required)
- `status: str` (required) — `"pending"` | `"in_progress"` | `"completed"` | `"skipped"`
- `notes: str` (optional)

**`update_profile`** — stores a user fact for cross-form pre-fill
- `field: str` (required) — profile key, e.g. `"first_name"`, `"email"`, `"service_address"`
- `value: str` (required)

---

## Form Schemas

### CPS Energy (`service_id: "cps_energy"`, 14 fields, 2 business-day lead time)

| # | Field name | Type | Required | Validator | Pre-fill from |
|---|---|---|---|---|---|
| 1 | first_name | text | yes | — | user.first_name |
| 2 | last_name | text | yes | — | user.last_name |
| 3 | date_of_birth | date | yes | — | user.date_of_birth |
| 4 | ssn_or_dl | secret | yes | ssn_or_dl | — |
| 5 | email | email | yes | email | user.email |
| 6 | phone | phone | yes | phone_us | user.phone |
| 7 | service_address | address | yes | address | user.service_address |
| 8 | service_city | text | yes | — | user.service_city (default: "San Antonio") |
| 9 | service_state | text | yes | — | — (default: "TX") |
| 10 | service_zip | text | yes | zip_us | user.service_zip |
| 11 | requested_start_date | date | yes | lead_time_2bd | — |
| 12 | is_military_relocation | boolean | no | — | — (default: false) |
| 13 | wants_paperless | boolean | no | — | — (default: true) |
| 14 | wants_budget_billing | boolean | no | — | — (default: false) |

### SAWS (`service_id: "saws"`, 14 fields, 5 business-day lead time)

| # | Field name | Type | Required | Validator | Pre-fill from |
|---|---|---|---|---|---|
| 1 | first_name | text | yes | — | user.first_name |
| 2 | last_name | text | yes | — | user.last_name |
| 3 | date_of_birth | date | yes | — | user.date_of_birth |
| 4 | ssn_last4 | secret | yes | ssn_last4 | — |
| 5 | email | email | yes | email | user.email |
| 6 | phone | phone | yes | phone_us | user.phone |
| 7 | service_address | address | yes | address | user.service_address |
| 8 | service_city | text | yes | — | user.service_city (default: "San Antonio") |
| 9 | service_state | text | yes | — | — (default: "TX") |
| 10 | service_zip | text | yes | zip_us | user.service_zip |
| 11 | requested_start_date | date | yes | lead_time_5bd | — |
| 12 | residency_proof_type | select | yes | — | — (options: Lease agreement, Closing documents, Utility bill in your name) |
| 13 | letter_of_credit_available | boolean | no | — | — (default: false) |
| 14 | is_dv_survivor_waiver | boolean | no | — | — (default: false) |

### City of San Antonio Solid Waste (`service_id: "cosa_solid_waste"`, 10 fields, 0-day lead time)

| # | Field name | Type | Required | Validator | Pre-fill from |
|---|---|---|---|---|---|
| 1 | first_name | text | yes | — | user.first_name |
| 2 | last_name | text | yes | — | user.last_name |
| 3 | phone | phone | yes | phone_us | user.phone |
| 4 | service_address | address | yes | address | user.service_address |
| 5 | service_zip | text | yes | zip_us | user.service_zip |
| 6 | cps_account_number | text | no | cps_account | — |
| 7 | carts_present | select | yes | — | — (options: Yes all three, Only some of them, No carts at all, Not sure yet) |
| 8 | preferred_brown_cart_size | select | yes | — | — (default: Medium 64 gallon) |
| 9 | wants_collection_day_lookup | boolean | no | — | — (default: true) |
| 10 | wants_text_alerts | boolean | no | — | — (default: false) |

---

## Workflow FSM — Command Reference

During an active form workflow, the orchestrator intercepts these commands before passing input to the field validator:

| Command | Phase | Effect |
|---|---|---|
| `keep` | Field entry | Accept pre-filled value, advance to next field |
| `keep all` | Field entry | Accept all consecutive pre-filled fields, stop at first gap |
| `skip` | Field entry (optional fields only) | Store empty string, advance |
| `undo` / `go back` / `back` | Field entry | Decrement index, clear value and error |
| `pause` / `wait` / `hold on` / `stop` | Field entry | Detach workflow (keep persisted state); user can resume later |
| `cancel` / `abort` / `quit form` / `quit` | Field entry or summary | Clear workflow and persisted state |
| `submit` | Summary | Commit values to profile, mark service completed |
| `edit <field_name>` | Summary | Jump back to named field |
| `resume <service_id>` | Idle | Restore paused workflow from persisted state |
| `show checklist` / `show my checklist` | Any | Show checklist without disrupting workflow state |
| `yes` (or equivalent) | Pending confirmation | Start the staged workflow |

---

## Configuration Reference

All settings are environment variables with defaults. No `.env` file is required; set variables in the shell or via Docker Compose.

| Variable | Default | Description |
|---|---|---|
| `ALAMO_OUTPUT_DIR` | `<project_root>/output` | Indices, logs, user state |
| `ALAMO_DATA_DIR` | `<project_root>/data` | `form_schemas.json` location |
| `ALAMO_INDEX_DIR` | `<output>/index` | FAISS index files |
| `ALAMO_SAU_ROOT` | `<project_root>/sa_utilities` | SA Utilities package root |
| `ALAMO_SAU_CHUNKS` | `<sau_root>/data/chunks/all_chunks.json` | Chunk metadata file |
| `ALAMO_SAU_CHROMA` | `<sau_root>/data/chroma` | ChromaDB persistent directory |
| `ALAMO_SAU_COLLECTION` | `sa_utilities` | ChromaDB collection name |
| `ALAMO_USER_STATE` | `<output>/user_state.json` | User state file |
| `ALAMO_EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model ID |
| `ALAMO_EMBED_DIM` | `384` | Embedding dimension |
| `ALAMO_LLM_MODEL` | `llama-3.3-70b-instruct-awq` | LLM model name |
| `ALAMO_LLM_BASE_URL` | _(none)_ | OpenAI-compatible endpoint base URL |
| `ALAMO_LLM_API_KEY` | falls back to `OPENAI_API_KEY` | API key |
| `ALAMO_DEMO_MODE` | `"0"` (auto-`"1"` if no key) | Force rule-based demo mode |
| `ALAMO_TOP_K` | `5` | Passages returned per retrieval call |

---

## Persistence Schema (`output/user_state.json`)

```json
{
  "profile": {
    "user": {
      "first_name": "string",
      "last_name": "string",
      "email": "string",
      "phone": "(NXX) NXX-XXXX",
      "service_address": "123 Main St",
      "service_city": "San Antonio",
      "service_zip": "78205"
    }
  },
  "checklist": [
    {
      "service_id": "cps_energy",
      "name": "CPS Energy electric & gas",
      "status": "pending | in_progress | completed | skipped",
      "lead_time_days": 2,
      "form_id": "cps_energy_start",
      "completed_at": "2025-01-15T10:30:00 or null",
      "notes": ""
    }
  ],
  "active_workflow": {
    "service_id": "cps_energy",
    "current_field_index": 3,
    "values": {"first_name": "Alex", "last_name": "Kim"},
    "completed": false,
    "errors": {}
  },
  "history": [
    {"role": "user | assistant", "content": "...", "ts": "ISO8601"}
  ]
}
```

`active_workflow` is `null` when no form is in progress. History is capped at 200 entries.
