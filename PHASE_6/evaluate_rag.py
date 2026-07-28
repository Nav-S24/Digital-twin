"""
evaluate_rag.py
================
Lightweight evaluation harness for the Vehicle Knowledge Base RAG pipeline.

Runs every question in `test_queries.json` through retrieval (and, unless
--retrieval-only is passed, through Gemini generation too), measuring
retrieval latency and LLM latency separately, and writes a human-readable
Markdown report to `outputs/evaluation_report.md` (plus a machine-readable
`outputs/retrieval_metrics.json`).

This is intentionally a lightweight diagnostic tool, not a scored benchmark:
there is no ground-truth answer key, so it reports *what happened*
(latency, which chunks/sources were retrieved, whether the LLM was invoked
or short-circuited by the "no relevant context" guardrail) rather than an
automated correctness score. That keeps it honest about what it can and
cannot measure — see the report's "Limitations" section.

Usage:
    python evaluate_rag.py
    python evaluate_rag.py --queries test_queries.json --output outputs/evaluation_report.md
    python evaluate_rag.py --retrieval-only     # skip Gemini calls entirely
    python evaluate_rag.py --top-k 3
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.rag_pipeline import build_prompt, compute_confidence
from app.retriever import RetrievedChunk, retrieve
from app.services.gemini_service import call_gemini
from app.utils import get_logger

logger = get_logger(__name__)

DEFAULT_OUTPUT_DIR = Path("outputs")


# --- Result container -----------------------------------------------------------------

@dataclass
class QueryResult:
    id: str
    question: str
    category: str | None
    retrieval_ms: float
    llm_ms: float | None
    chunks: list[RetrievedChunk] = field(default_factory=list)
    answer: str | None = None
    confidence: float = 0.0
    error: str | None = None

    @property
    def total_ms(self) -> float:
        return self.retrieval_ms + (self.llm_ms or 0.0)

    def to_metrics_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "category": self.category,
            "retrieval_ms": round(self.retrieval_ms, 2),
            "llm_ms": round(self.llm_ms, 2) if self.llm_ms is not None else None,
            "chunk_count": len(self.chunks),
            "confidence": self.confidence,
            "error": self.error,
        }


# --- Core evaluation -----------------------------------------------------------------

def load_queries(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Query file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        queries = json.load(fh)
    logger.info("Loaded %d test quer(y/ies) from '%s'", len(queries), path)
    return queries


def evaluate_query(item: dict, top_k: int, retrieval_only: bool) -> QueryResult:
    question = item["question"]
    category = item.get("category")

    retrieval_start = time.perf_counter()
    try:
        chunks = retrieve(question, top_k=top_k, category=category)
    except Exception as exc:  # noqa: BLE001 - one bad query must not abort the whole run
        logger.error("Retrieval failed for '%s': %s", item.get("id", question), exc)
        return QueryResult(
            id=item.get("id", question), question=question, category=category,
            retrieval_ms=(time.perf_counter() - retrieval_start) * 1000,
            llm_ms=None, error=f"retrieval failed: {exc}",
        )
    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    if retrieval_only or not chunks:
        return QueryResult(
            id=item.get("id", question), question=question, category=category,
            retrieval_ms=retrieval_ms, llm_ms=None, chunks=chunks,
            answer=None if chunks else "(no chunks passed the relevance threshold)",
            confidence=compute_confidence(chunks),
        )

    llm_start = time.perf_counter()
    try:
        prompt = build_prompt(question, chunks)
        answer = call_gemini(prompt)
        llm_ms = (time.perf_counter() - llm_start) * 1000
        error = None
    except Exception as exc:  # noqa: BLE001 - keep evaluating remaining queries
        logger.error("LLM generation failed for '%s': %s", item.get("id", question), exc)
        answer, llm_ms, error = None, (time.perf_counter() - llm_start) * 1000, str(exc)

    return QueryResult(
        id=item.get("id", question), question=question, category=category,
        retrieval_ms=retrieval_ms, llm_ms=llm_ms, chunks=chunks,
        answer=answer, confidence=compute_confidence(chunks), error=error,
    )


def run_evaluation(queries: list[dict], top_k: int, retrieval_only: bool) -> list[QueryResult]:
    results: list[QueryResult] = []
    for i, item in enumerate(queries, start=1):
        logger.info("[%d/%d] Evaluating: %s", i, len(queries), item["question"])
        results.append(evaluate_query(item, top_k=top_k, retrieval_only=retrieval_only))
    return results


# --- Reporting -----------------------------------------------------------------

def _fmt_ms(value: float | None) -> str:
    return f"{value:.1f} ms" if value is not None else "n/a"


def _summarize_latencies(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0}
    sorted_vals = sorted(values)
    p95_index = min(len(sorted_vals) - 1, int(round(0.95 * (len(sorted_vals) - 1))))
    return {
        "count": len(values),
        "avg": statistics.mean(values),
        "min": min(values),
        "max": max(values),
        "p95": sorted_vals[p95_index],
    }


def build_metrics_json(results: list[QueryResult], top_k: int, retrieval_only: bool) -> dict:
    retrieval_latencies = [r.retrieval_ms for r in results]
    llm_latencies = [r.llm_ms for r in results if r.llm_ms is not None]
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "top_k": top_k,
        "mode": "retrieval-only" if retrieval_only else "full-rag",
        "embedding_model": settings.embedding_model,
        "llm_model": settings.llm_model,
        "retrieval_latency_ms": _summarize_latencies(retrieval_latencies),
        "llm_latency_ms": _summarize_latencies(llm_latencies),
        "zero_hit_queries": sum(1 for r in results if not r.chunks),
        "error_queries": sum(1 for r in results if r.error),
        "results": [r.to_metrics_dict() for r in results],
    }


def build_report(results: list[QueryResult], top_k: int, retrieval_only: bool) -> str:
    retrieval_latencies = [r.retrieval_ms for r in results]
    llm_latencies = [r.llm_ms for r in results if r.llm_ms is not None]
    zero_hit = [r for r in results if not r.chunks]
    errors = [r for r in results if r.error]

    retrieval_stats = _summarize_latencies(retrieval_latencies)
    llm_stats = _summarize_latencies(llm_latencies)

    lines: list[str] = []
    lines.append("# RAG Evaluation Report")
    lines.append("")
    lines.append(f"- **Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **Queries evaluated:** {len(results)}")
    lines.append(f"- **top_k:** {top_k}")
    lines.append(f"- **Mode:** {'retrieval-only (no LLM calls)' if retrieval_only else 'full RAG (retrieval + Gemini)'}")
    lines.append(f"- **Embedding model:** `{settings.embedding_model}`")
    lines.append(f"- **LLM model:** `{settings.llm_model}`")
    lines.append(f"- **Vector store:** `{settings.persist_dir}` (collection: `{settings.collection_name}`)")
    lines.append("")

    lines.append("## Latency Summary")
    lines.append("")
    lines.append("| Stage | Count | Avg | Min | Max | P95 |")
    lines.append("|---|---|---|---|---|---|")
    lines.append(
        f"| Retrieval | {retrieval_stats['count']} | {_fmt_ms(retrieval_stats['avg'])} | "
        f"{_fmt_ms(retrieval_stats['min'])} | {_fmt_ms(retrieval_stats['max'])} | {_fmt_ms(retrieval_stats['p95'])} |"
    )
    if llm_stats["count"]:
        lines.append(
            f"| LLM generation | {llm_stats['count']} | {_fmt_ms(llm_stats['avg'])} | "
            f"{_fmt_ms(llm_stats['min'])} | {_fmt_ms(llm_stats['max'])} | {_fmt_ms(llm_stats['p95'])} |"
        )
    else:
        lines.append("| LLM generation | 0 | n/a | n/a | n/a | n/a |")
    lines.append("")

    lines.append("## Retrieval Health")
    lines.append("")
    lines.append(f"- Queries with **zero** chunks above the similarity threshold: {len(zero_hit)}/{len(results)}")
    lines.append(f"- Queries that raised an error: {len(errors)}/{len(results)}")
    lines.append("")

    lines.append("## Per-Query Results")
    lines.append("")
    lines.append("| ID | Question | Retrieval | LLM | Chunks | Top Source | Confidence | Status |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        top_source = "-"
        if r.chunks:
            top = r.chunks[0]
            top_source = f"{top.metadata.get('file_name', 'unknown')} (p.{top.metadata.get('page', '?')})"
        status = "ERROR" if r.error else ("NO CONTEXT" if not r.chunks else "OK")
        question_short = (r.question[:60] + "…") if len(r.question) > 60 else r.question
        lines.append(
            f"| {r.id} | {question_short} | {_fmt_ms(r.retrieval_ms)} | {_fmt_ms(r.llm_ms)} | "
            f"{len(r.chunks)} | {top_source} | {r.confidence:.2f} | {status} |"
        )
    lines.append("")

    if errors:
        lines.append("## Errors")
        lines.append("")
        for r in errors:
            lines.append(f"- **{r.id}** (`{r.question}`): {r.error}")
        lines.append("")

    lines.append("## Sample Answers")
    lines.append("")
    sample_count = 0
    for r in results:
        if r.answer and not r.error and sample_count < 5:
            lines.append(f"**Q ({r.id}):** {r.question}")
            lines.append("")
            lines.append(f"> {r.answer}")
            lines.append("")
            sample_count += 1
    if sample_count == 0:
        lines.append("_No generated answers to show (retrieval-only mode, or no LLM responses succeeded)._")
        lines.append("")

    lines.append("## Limitations of This Report")
    lines.append("")
    lines.append(
        "- There is no ground-truth answer key here, so this report measures **latency and "
        "retrieval behavior**, not factual correctness of generated answers."
    )
    lines.append(
        "- `Confidence` is the retrieval-based proxy from `rag_pipeline.compute_confidence` "
        "(best cosine distance among retrieved chunks), not a verified accuracy score."
    )
    lines.append(
        "- Results depend entirely on what has been ingested into the vector store — run "
        "`python build_vectordb.py` first to index your PDFs, or all queries will show `NO CONTEXT`."
    )
    lines.append("")

    return "\n".join(lines)


# --- CLI -----------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the Vehicle Knowledge Base RAG pipeline.")
    parser.add_argument("--queries", type=Path, default=Path("test_queries.json"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "evaluation_report.md")
    parser.add_argument("--metrics-output", type=Path, default=DEFAULT_OUTPUT_DIR / "retrieval_metrics.json")
    parser.add_argument("--top-k", type=int, default=settings.top_k)
    parser.add_argument(
        "--retrieval-only", action="store_true",
        help="Skip Gemini calls entirely — measure retrieval latency/quality only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queries = load_queries(args.queries)
    results = run_evaluation(queries, top_k=args.top_k, retrieval_only=args.retrieval_only)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(results, top_k=args.top_k, retrieval_only=args.retrieval_only)
    args.output.write_text(report, encoding="utf-8")
    logger.info("Evaluation report written to '%s'", args.output)

    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics = build_metrics_json(results, top_k=args.top_k, retrieval_only=args.retrieval_only)
    args.metrics_output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info("Retrieval metrics written to '%s'", args.metrics_output)

    print(report)


if __name__ == "__main__":
    main()
