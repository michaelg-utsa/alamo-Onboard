# Logging Guide

## Overview

AlamoOnboard emits structured JSON log lines to stdout. Every entry has these fields:

```json
{
  "timestamp": "2026-05-04T14:23:01.412+00:00",
  "level": "INFO",
  "module": "src.agent.orchestrator",
  "request_id": "a3f1c2d7",
  "message": "user message received, len=28"
}
```

Each user turn generates a fresh `request_id` (8-character hex UUID prefix) at the top of `AlamoAgent.handle_user_message()`. This ID is stored in a `contextvars.ContextVar` and included in every log call made by any component during that turn — orchestrator, LLM client, tools, retriever — without needing to pass it explicitly.

## Viewing Logs

```bash
# Live tail (Docker)
docker compose logs -f app

# Filter for one request
docker compose logs app | grep '"request_id": "a3f1c2d7"'

# Pretty-print one request's trace
docker compose logs app | python -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line)
        if e.get('request_id') == 'a3f1c2d7':
            print(f\"{e['timestamp']} [{e['level']}] {e['module']}: {e['message']}\")
    except: pass
"
```

## Worked Example: Tracing One Request End-to-End

The user typed: `What is the deposit for CPS Energy?`

The resulting request_id assigned was `a3f1c2d7`.

```json
{"timestamp":"2026-05-04T14:23:01.412+00:00","level":"INFO","module":"src.agent.orchestrator","request_id":"a3f1c2d7","message":"user message received, len=39"}
{"timestamp":"2026-05-04T14:23:01.415+00:00","level":"INFO","module":"src.agent.orchestrator","request_id":"a3f1c2d7","message":"routing to LLM turn"}
{"timestamp":"2026-05-04T14:23:01.820+00:00","level":"INFO","module":"src.agent.llm_client","request_id":"a3f1c2d7","message":"sending chat request model=llama-3.3-70b-instruct-awq messages=3 tools=5"}
{"timestamp":"2026-05-04T14:23:02.104+00:00","level":"INFO","module":"src.agent.llm_client","request_id":"a3f1c2d7","message":"received tool_calls count=1"}
{"timestamp":"2026-05-04T14:23:02.106+00:00","level":"INFO","module":"src.agent.tools","request_id":"a3f1c2d7","message":"tool call: retrieve_knowledge query='CPS Energy deposit' k=5"}
{"timestamp":"2026-05-04T14:23:02.108+00:00","level":"INFO","module":"src.indexer.retriever","request_id":"a3f1c2d7","message":"hybrid search query='CPS Energy deposit' k=5"}
{"timestamp":"2026-05-04T14:23:02.110+00:00","level":"INFO","module":"src.indexer.embedder","request_id":"a3f1c2d7","message":"encoding 1 texts with all-MiniLM-L6-v2"}
{"timestamp":"2026-05-04T14:23:02.198+00:00","level":"INFO","module":"src.indexer.retriever","request_id":"a3f1c2d7","message":"dense hits=10 bm25_top=10 rrf_merged=14 filtered=5 source_filter=None"}
{"timestamp":"2026-05-04T14:23:02.200+00:00","level":"INFO","module":"src.agent.tools","request_id":"a3f1c2d7","message":"retrieve_knowledge returned 5 passages top_source='CPS Energy'"}
{"timestamp":"2026-05-04T14:23:02.202+00:00","level":"INFO","module":"src.agent.llm_client","request_id":"a3f1c2d7","message":"sending chat request model=llama-3.3-70b-instruct-awq messages=5 tools=5"}
{"timestamp":"2026-05-04T14:23:02.891+00:00","level":"INFO","module":"src.agent.llm_client","request_id":"a3f1c2d7","message":"received content len=312 tool_calls=0"}
{"timestamp":"2026-05-04T14:23:02.893+00:00","level":"INFO","module":"src.agent.orchestrator","request_id":"a3f1c2d7","message":"reply generated checklist_changed=False"}
{"timestamp":"2026-05-04T14:23:02.896+00:00","level":"INFO","module":"src.checklist.tracker","request_id":"a3f1c2d7","message":"history appended role=assistant len=312"}
```

### What the Trace Shows

| Log line | Component | What happened |
|---|---|---|
| `user message received` | orchestrator | Turn started, request_id assigned |
| `routing to LLM turn` | orchestrator | No active workflow; going to LLM |
| `sending chat request` (first) | llm_client | LLM called with system prompt + history + user message |
| `received tool_calls count=1` | llm_client | LLM requested retrieve_knowledge |
| `tool call: retrieve_knowledge` | tools | ToolBox dispatched the call |
| `hybrid search` | retriever | BM25+FAISS search initiated |
| `encoding 1 texts` | embedder | Query vector generated |
| `dense hits=10 bm25_top=10` | retriever | Both arms searched, RRF applied |
| `retrieve_knowledge returned 5 passages` | tools | Tool result ready |
| `sending chat request` (second) | llm_client | LLM called again with tool result |
| `received content len=312` | llm_client | Final answer generated |
| `reply generated` | orchestrator | Turn complete |
| `history appended` | tracker | Turn saved to user_state.json |

## Log Levels

| Level | When used |
|---|---|
| `DEBUG` | Detailed internals (not emitted in default INFO level) |
| `INFO` | Every significant step in a request (tool calls, routing decisions, model calls) |
| `WARNING` | Recoverable issues (unknown source labels, ChromaDB missing chunks, etc.) |
| `ERROR` | Tool failures, JSON parse errors (request continues if possible) |
| `CRITICAL` | Unrecoverable startup failures |

## Configuration

```python
# src/utils/logging_utils.py
setup_logging(level=logging.INFO, log_file=Path("output/logs/app.log"))
```

Log files are written to `output/logs/` (mounted as a Docker volume so they persist across restarts). Each line is a self-contained JSON object, making them suitable for ingestion into log aggregators (Datadog, CloudWatch, Loki, etc.).
