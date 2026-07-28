"""
rag_pipeline.py
================
The generation layer: takes a question, retrieves grounding context via
retriever.py, assembles a strict grounded prompt (templates loaded from
app/prompts/), calls Gemini via app.services.gemini_service, and returns a
structured result with sources and a confidence score.

Every guardrail here exists to reduce hallucination for a
vehicle-safety-adjacent domain — most importantly, the LLM is never called
at all when retrieval finds nothing relevant (see run_rag_pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.config import settings
from app.retriever import RetrievedChunk, retrieve
from app.services.gemini_service import call_gemini
from app.utils import get_logger, timed

logger = get_logger(__name__)


# --- Prompt template loading -----------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_system_instruction() -> str:
    return (settings.prompts_dir / "system_prompt.txt").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def _load_prompt_template() -> str:
    return (settings.prompts_dir / "rag_prompt.txt").read_text(encoding="utf-8")


def format_context(chunks: list[RetrievedChunk]) -> str:
    """
    Formats retrieved chunks into a numbered, source-labeled context block.
    The numbering here is what the prompt asks the model to cite back
    (e.g. "[Source 2]"), which is what makes source attribution in the
    final answer traceable to an actual chunk/page.
    """
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        file_name = chunk.metadata.get("file_name", "unknown")
        page = chunk.metadata.get("page", "?")
        section = chunk.metadata.get("section_title")
        header = f"[Source {i}] {file_name}, page {page}" + (f" — {section}" if section else "")
        blocks.append(f"{header}\n{chunk.text.strip()}")
    return "\n\n".join(blocks)


def build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    return _load_prompt_template().format(
        system_instruction=_load_system_instruction(),
        context=format_context(chunks),
        question=question.strip(),
    )


# --- Confidence -----------------------------------------------------------------

def compute_confidence(chunks: list[RetrievedChunk]) -> float:
    """
    Retrieval-based confidence proxy: maps the best (lowest) cosine
    distance among retrieved chunks into a bounded 0-1 score. This is a
    retrieval-only signal — it says "how well did we find relevant
    context," not "how correct is the generated answer." Documented as a
    known limitation rather than treated as a true answer-correctness score.
    """
    if not chunks:
        return 0.0
    best_distance = min(chunk.score for chunk in chunks)
    confidence = 1.0 - (best_distance / 2.0)
    return max(0.0, min(1.0, round(confidence, 4)))


# --- Result container -----------------------------------------------------------------

@dataclass
class RagResult:
    answer: str
    sources: list[RetrievedChunk]
    confidence: float


# --- Orchestration -----------------------------------------------------------------

NO_CONTEXT_ANSWER = (
    "I don't have enough information in the knowledge base to answer that question. "
    "Try rephrasing, narrowing the question, or check that the relevant documents "
    "have been ingested."
)


@timed("RAG pipeline")
def run_rag_pipeline(
    question: str,
    top_k: int | None = None,
    category: str | None = None,
) -> RagResult:
    """
    Full RAG orchestration:
        1. Retrieve grounding chunks (already threshold-filtered by retriever.py).
        2. If nothing relevant was found, short-circuit and never call the LLM
           at all — this is the main hallucination guardrail: a model cannot
           fabricate an answer to a call it never receives.
        3. Otherwise, build the strict grounded prompt and call Gemini.
        4. Return the answer alongside the sources actually used and a
           retrieval-based confidence score.
    """
    if not question or not question.strip():
        raise ValueError("question must not be blank")

    chunks = retrieve(question, top_k=top_k, category=category)

    if not chunks:
        logger.info("No chunks passed the relevance threshold — skipping LLM call.")
        return RagResult(answer=NO_CONTEXT_ANSWER, sources=[], confidence=0.0)

    prompt = build_prompt(question, chunks)
    answer = call_gemini(prompt)
    confidence = compute_confidence(chunks)

    return RagResult(answer=answer, sources=chunks, confidence=confidence)
