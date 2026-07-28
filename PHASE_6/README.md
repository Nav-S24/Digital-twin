# Vehicle Knowledge Base — Phase 6 (RAG)

Part of **Personalized Vehicle Brain & Health Digital Twin with Natural Language Intelligence**.

A production-structured Retrieval-Augmented Generation (RAG) service that answers questions
about vehicle manuals, OBD-II fault codes, service procedures, and maintenance guidelines,
grounded strictly in ingested documents — the LLM is never allowed to answer from its own
trained knowledge, only from retrieved context.

---

## 0. What changed in this review

This phase previously shipped with correct architecture but two real bugs and an
empty knowledge base (`data/*/` held only `.gitkeep` placeholders). Fixed here:

1. **Embedding crash (critical).** `HuggingFaceEmbeddings` was constructed with a
   `query_instruction` kwarg that doesn't exist on any version of
   `langchain_huggingface` (checked 0.0.3 through 1.2.2) — every ingestion or
   query call raised a pydantic `ValidationError` before touching the vector
   store. Removed (`app/services/embedding_service.py`).
2. **`None` metadata crash (critical).** `guess_section_title()` returns `None`
   when a page's first line doesn't look like a heading (the common case for any
   page starting directly with body text). That `None` was written straight into
   chunk metadata, but ChromaDB's validator only accepts `str`/`int`/`float`/`bool`
   — ingestion crashed on every such page. Coerced to `""` (`app/services/document_service.py`).
3. **Real content added.** `data/manuals/`, `data/obd_docs/`, `data/service_guides/`,
   `data/maintenance_guides/` now contain 4 real PDFs (93 pages, 213 chunks) — an
   original general vehicle owner's-manual reference, a curated OBD-II diagnostic
   reference built from this project's own Critical/High-severity code data, and
   original service-procedure and maintenance-interval guides. See
   `original_notebook/` equivalent note below for provenance — none of this is
   copied from a copyrighted manual.
4. **New: offline embedding fallback (`EMBEDDING_BACKEND=tfidf`).** The default
   `huggingface` backend needs a one-time model download from `huggingface.co`,
   which isn't reachable in every environment (e.g. network-restricted CI). Added
   `app/services/tfidf_embeddings.py`, a fully offline TF-IDF-based alternative —
   lexical, not semantic, similarity, so retrieval quality is lower, but it lets
   the *entire* pipeline (ingest → embed → store → retrieve → prompt) run and be
   tested with zero external downloads. Switch back to `huggingface` for
   production use whenever internet access is available. **If using `tfidf`,
   also raise `SIMILARITY_THRESHOLD` to ~1.0–1.2** — TF-IDF's cosine-distance
   geometry isn't calibrated the same way as the semantic backend's, and the
   default 0.8 threshold silently drops every result for natural-language
   questions under `tfidf` (see `app/config.py` for the full explanation).

Both the `huggingface` and `tfidf` backends were verified end-to-end against the
real PDFs above: 211 chunks embedded and persisted, and retrieval returns
genuinely relevant results for real queries (e.g. "engine overheating temperature"
→ the correct coolant-sensor DTC entries).

---

## 1. Project Overview

| | |
|---|---|
| **Goal** | Turn a folder of vehicle PDFs (owner's manuals, OBD-II code references, service guides, maintenance schedules) into a queryable, source-cited Q&A API. |
| **Approach** | Classic RAG: chunk & embed documents once (offline), retrieve the most relevant chunks per query (online), and ground an LLM's answer strictly in that retrieved context. |
| **Why grounding matters here** | This is a vehicle-safety-adjacent domain — a hallucinated torque spec or a fabricated DTC meaning is a real-world safety risk, not just an inconvenience. The pipeline never lets the LLM answer without supporting context (see `app/rag_pipeline.py`). |
| **Phase in the larger project** | Phase 6 of the "Personalized Vehicle Brain & Health Digital Twin" project. Phase 7 will build an LLM-driven vehicle assistant on top of this API. |

---

## 2. Architecture

```
data/*.pdf  →  app/ingest.py  →  vectordb/chroma_db (ChromaDB)  →  app/retriever.py
                     │                                                    │
          app/services/document_service.py                 app/services/vector_store.py
          app/services/embedding_service.py                               │
                                                                            ▼
                                                                  app/rag_pipeline.py
                                                        (prompt from app/prompts/ + Gemini
                                                         via app/services/gemini_service.py)
                                                                            │
                                                                            ▼
                                                                    app/api.py (FastAPI)
```

## 3. Project Structure

```
PHASE_6_RAG/
├── app/
│   ├── api.py                    # FastAPI endpoints
│   ├── config.py                 # Settings, loaded from env / .env
│   ├── ingest.py                 # Ingestion orchestration (CLI: python -m app.ingest)
│   ├── retriever.py              # Query-time retrieval (similarity / MMR + threshold)
│   ├── rag_pipeline.py           # Prompt assembly + generation + confidence scoring
│   ├── prompts/
│   │   ├── system_prompt.txt     # Grounding rules given to Gemini
│   │   └── rag_prompt.txt        # {system_instruction}/{context}/{question} template
│   ├── services/
│   │   ├── embedding_service.py  # Cached HuggingFace embedding model
│   │   ├── vector_store.py       # All ChromaDB read/write access
│   │   ├── gemini_service.py     # All Gemini API calls (retry/timeout/auth)
│   │   └── document_service.py   # PDF loading, chunking, deduplication
│   ├── models/
│   │   ├── request_models.py     # AskRequest, SearchRequest
│   │   └── response_models.py    # AskResponse, SearchResponse, etc.
│   └── utils/
│       ├── logger.py             # get_logger(), @timed()
│       ├── helpers.py            # content_hash, section/scan heuristics
│       └── file_utils.py         # PDF discovery, category inference
├── data/                         # manuals / obd_docs / service_guides / maintenance_guides
├── vectordb/chroma_db/           # persisted ChromaDB collection (generated)
├── logs/app.log                  # generated at runtime
├── tests/                        # pytest suite (all external services mocked)
├── outputs/                      # evaluate_rag.py writes its report + metrics here
├── build_vectordb.py             # CLI: build/update the vector store
├── evaluate_rag.py               # CLI: run test_queries.json through the pipeline
├── test_queries.json             # 15 evaluation questions
├── requirements.txt
├── .env.example / .env
└── README.md
```

---

## 4. Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then set GOOGLE_API_KEY inside .env
```

Drop additional PDFs into the matching `data/` subfolder (`manuals/`, `obd_docs/`,
`service_guides/`, `maintenance_guides/` — or any other subfolder name, which
becomes that document's `category`) — the folders already contain a starter set
(93 pages / 213 chunks, see section 0).

If `huggingface.co` isn't reachable from your environment, set
`EMBEDDING_BACKEND=tfidf` (and raise `SIMILARITY_THRESHOLD` to ~1.0–1.2) to run
the whole pipeline fully offline instead — see section 0 for details.

## 5. Build the vector store

```bash
python build_vectordb.py
# or, with overrides:
python build_vectordb.py --chunk-size 800 --chunk-overlap 150
```

Re-running is safe — chunks are deduplicated by content hash, so only new
or changed content is added.

## 6. Run the API

```bash
uvicorn app.api:app --reload
```

| Endpoint | Method | Purpose |
|---|---|---|
| `/ask` | POST | Full RAG: retrieve + Gemini generation → `{answer, sources, confidence}` |
| `/search` | POST | Retrieval-only debug endpoint (no LLM call) |
| `/documents` | GET | Lists indexed documents and per-file chunk counts |
| `/health` | GET | Vector store load status + chunk count |

Interactive docs: `http://localhost:8000/docs`

## 7. Evaluate

```bash
python evaluate_rag.py                 # full RAG (retrieval + Gemini)
python evaluate_rag.py --retrieval-only # skip Gemini calls
```

Writes `outputs/evaluation_report.md` (human-readable) and
`outputs/retrieval_metrics.json` (machine-readable latency/retrieval stats).
This is a diagnostic tool, not a scored benchmark — there's no ground-truth
answer key, so it reports latency and retrieval behavior, not answer
correctness (see the report's own "Limitations" section).

## 8. Tests

```bash
pytest
```

Every test mocks out ChromaDB, the embedding model, and Gemini, so the
suite runs offline with no API key and no built vector store required.

## 9. Key design decisions

- **Never hallucinate silently.** If retrieval finds nothing above the
  similarity threshold, `rag_pipeline.run_rag_pipeline` returns a fixed
  "not enough information" answer *without calling the LLM at all*.
- **Single source of embedding config.** `app/services/embedding_service.py`
  is the only place the HuggingFace model is constructed, so ingestion and
  query-time embeddings can never silently drift apart.
- **Content-hash deduplication.** Re-running ingestion on the same or
  overlapping PDFs never creates duplicate chunks.
- **Confidence is a retrieval proxy, not an accuracy score.** It's derived
  from the best cosine distance among retrieved chunks — documented as a
  known limitation in both `rag_pipeline.py` and the evaluation report.
