# Model Documentation

## Embedding Model

| Field | Value |
|---|---|
| **Model ID** | `sentence-transformers/all-MiniLM-L6-v2` |
| **Source** | HuggingFace Hub: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 |
| **Version / commit** | Pinned at `HuggingFace Hub revision: main` (SHA pinned in `grading/manifest.yaml`) |
| **License** | Apache 2.0 |
| **Parameters** | 22.7M |
| **Embedding dimension** | 384 |
| **Architecture** | 6-layer MiniLM distilled from BERT; sentence-pair trained on 1B+ sentence pairs |
| **Download size** | ~91 MB |
| **Usage** | Offline: encode all document chunks during SA Utilities pipeline (batch size 64). Online: encode each user query at search time. Both use the same model to guarantee embedding space alignment. |
| **Normalization** | L2-normalized to unit length so inner-product equals cosine similarity in FAISS |
| **Cached at** | `~/.cache/huggingface/hub/` (standard HuggingFace cache; also cached in Docker layer) |

**Why this model:** Fast, high-quality semantic embeddings on CPU; Apache 2.0 license; 384 dimensions keep the FAISS index small; strong MTEB benchmark scores relative to size. No API key required.

---

## LLM (Default)

| Field | Value |
|---|---|
| **Model ID** | `llama-3.3-70b-instruct-awq` |
| **Source** | Served at `ALAMO_LLM_BASE_URL` via OpenAI-compatible chat completions API |
| **Architecture** | Meta Llama 3.3 70B Instruct, AWQ 4-bit quantized |
| **License** | Meta Llama 3.3 Community License (https://llama.meta.com/llama3_3/) |
| **Usage** | Multi-turn conversational responses; tool-calling for retrieval, checklist updates, form workflow triggers; temperature 0.2 |
| **Fallback** | If `ALAMO_LLM_API_KEY` is not set, `LLMClient` switches to demo mode: rule-based stub that calls `retrieve_knowledge` and summarizes results |
| **Configurability** | Model name, base URL, and API key are all env-var overrides — any OpenAI-compatible model can be substituted |

**Why this model:** Course-provided endpoint; 70B parameters produce high-quality instruction following and tool use; AWQ quantization fits on a single A100.

---

## Model Card Summary

See `docs/MODEL_CARD.md` for the full model card including intended use, limitations, risks, and out-of-scope uses.
