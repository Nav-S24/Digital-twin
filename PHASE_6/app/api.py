"""
api.py
======
FastAPI application for the Vehicle Knowledge Base (RAG).

Endpoints:
    POST /ask         - full RAG query: retrieve -> generate (Gemini) ->
                         {answer, sources, confidence}
    POST /search       - retrieval-only debug endpoint: raw chunks,
                         metadata, and similarity scores, no generation
    GET  /documents     - lists distinct documents currently indexed
    GET  /health        - service health check

Design note on sync vs async:
    Endpoint handlers below are declared as plain `def`, not `async def`.
    The actual work per request (embedding a query, searching Chroma,
    calling the Gemini API) is blocking I/O/CPU work with no async-native
    client used here. FastAPI automatically runs plain `def` endpoints in
    a threadpool, which keeps the event loop free for other requests
    instead of blocking it — the correct choice for this workload without
    rewriting the whole stack around async clients.

Run with:
    uvicorn app.api:app --reload
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.models.request_models import AskRequest, SearchRequest
from app.models.response_models import (
    AskResponse,
    DocumentsResponse,
    DocumentSummary,
    HealthResponse,
    SearchResponse,
    SearchResultItem,
    SourceItem,
)
from app.rag_pipeline import RagResult, run_rag_pipeline
from app.retriever import RetrievedChunk, retrieve
from app.services.vector_store import list_indexed_documents, load_vector_store
from app.utils import get_logger

logger = get_logger(__name__)


# --- Lifespan -----------------------------------------------------------------

class AppState:
    vector_store_loaded: bool = False
    startup_error: Optional[str] = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up: loading vector store...")
    try:
        load_vector_store()
        state.vector_store_loaded = True
        logger.info("Vector store loaded successfully.")
    except Exception as exc:  # noqa: BLE001 - startup must not crash the process
        state.startup_error = str(exc)
        logger.error("Vector store failed to load at startup: %s", exc)
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Vehicle Knowledge Base API",
    description=(
        "Production RAG API for vehicle manuals, OBD-II documentation, service "
        "procedures, and maintenance guidelines. Part of the 'Personalized "
        "Vehicle Brain & Health Digital Twin' Final Year Engineering Project."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


# --- Helpers -----------------------------------------------------------------

def require_vector_store() -> None:
    if not state.vector_store_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vector store is not available. {state.startup_error or ''}".strip(),
        )


def chunk_to_source_item(chunk: RetrievedChunk) -> SourceItem:
    return SourceItem(
        file_name=chunk.metadata.get("file_name", "unknown"),
        category=chunk.metadata.get("category", "uncategorized"),
        page=chunk.metadata.get("page"),
        section_title=chunk.metadata.get("section_title"),
        chunk_id=chunk.metadata.get("chunk_id"),
        score=chunk.score,
    )


def rag_result_to_response(result: RagResult) -> AskResponse:
    return AskResponse(
        answer=result.answer,
        sources=[chunk_to_source_item(c) for c in result.sources],
        confidence=result.confidence,
    )


# --- Exception handlers -----------------------------------------------------------------

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    logger.warning("Bad request on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
    logger.error("Missing resource on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    # Covers Gemini configuration/generation failures raised from rag_pipeline.py
    logger.error("Runtime failure on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred while processing the request."},
    )


# --- Endpoints -----------------------------------------------------------------

@app.post("/ask", response_model=AskResponse, tags=["RAG"])
def ask(payload: AskRequest) -> AskResponse:
    """Run the full RAG pipeline: retrieve context, generate a grounded answer via Gemini, return sources + confidence."""
    require_vector_store()
    start = time.perf_counter()

    result = run_rag_pipeline(payload.question, top_k=payload.top_k, category=payload.category)

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "Answered question in %.1f ms | confidence=%.2f | sources=%d",
        elapsed_ms, result.confidence, len(result.sources),
    )
    return rag_result_to_response(result)


@app.post("/search", response_model=SearchResponse, tags=["Retrieval"])
def search(payload: SearchRequest) -> SearchResponse:
    """Retrieval-only endpoint: raw chunks, metadata, and similarity scores. No generation."""
    require_vector_store()
    chunks = retrieve(
        payload.query,
        top_k=payload.top_k,
        category=payload.category,
        search_type=payload.search_type,
    )
    results = [SearchResultItem(text=c.text, metadata=c.metadata, score=c.score) for c in chunks]
    return SearchResponse(query=payload.query, results=results)


@app.get("/documents", response_model=DocumentsResponse, tags=["Metadata"])
def documents(category: Optional[str] = None) -> DocumentsResponse:
    """Lists distinct documents currently indexed, with category and chunk count."""
    require_vector_store()
    docs = list_indexed_documents(category=category)
    return DocumentsResponse(
        total_documents=len(docs),
        documents=[DocumentSummary(**d) for d in docs],
    )


@app.get("/health", response_model=HealthResponse, tags=["Metadata"])
def health() -> HealthResponse:
    """Reports whether the vector store loaded successfully and how many chunks it holds."""
    if not state.vector_store_loaded:
        return HealthResponse(
            status="unhealthy",
            vector_store_loaded=False,
            chunk_count=0,
            detail=state.startup_error or "Vector store not loaded.",
        )
    try:
        store = load_vector_store()
        chunk_count = store._collection.count()  # noqa: SLF001 - no public count API in Chroma
    except Exception as exc:  # noqa: BLE001
        return HealthResponse(
            status="degraded", vector_store_loaded=True, chunk_count=0,
            detail=f"Vector store loaded but count check failed: {exc}",
        )
    return HealthResponse(status="healthy", vector_store_loaded=True, chunk_count=chunk_count)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True)
