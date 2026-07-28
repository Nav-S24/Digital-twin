"""
tfidf_embeddings.py
=====================
A fully-offline, LangChain-compatible ``Embeddings`` implementation backed
by scikit-learn's ``TfidfVectorizer``. No model download is required, so
this works in network-restricted environments where huggingface.co isn't
reachable.

This is a fallback, not a replacement: TF-IDF captures lexical overlap
(shared words/phrases), not deep semantic similarity, so retrieval quality
is noticeably lower than the default BGE embedding model - e.g. a query for
"why is my car overheating" won't match a chunk that only says "engine
temperature exceeds normal range" the way a true semantic embedding would.
Use the default ``huggingface`` backend whenever internet access to
huggingface.co is available; use ``tfidf`` (via ``EMBEDDING_BACKEND=tfidf``)
only when it isn't.

Because a TF-IDF vectorizer's vocabulary must be identical between the
vectors written at ingestion time and the vector computed for a query at
retrieval time, the fitted vectorizer is persisted to disk (next to the
Chroma collection) the first time ``embed_documents`` is called, and
reloaded by ``embed_query`` on every subsequent process.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from langchain_core.embeddings import Embeddings

from app.utils import get_logger

logger = get_logger(__name__)

_VECTORIZER_FILENAME = "tfidf_vectorizer.joblib"


class TfidfEmbeddings(Embeddings):
    """Minimal Embeddings interface (embed_documents / embed_query) that
    LangChain's Chroma wrapper expects, implemented with TF-IDF instead of
    a neural embedding model."""

    def __init__(self, persist_dir: Path, max_features: int = 512):
        self.persist_dir = Path(persist_dir)
        self.max_features = max_features
        self._vectorizer = None

    @property
    def _vectorizer_path(self) -> Path:
        return self.persist_dir / _VECTORIZER_FILENAME

    def _load_fitted_vectorizer(self):
        import joblib

        if not self._vectorizer_path.exists():
            raise RuntimeError(
                f"No fitted TF-IDF vectorizer found at {self._vectorizer_path}. "
                "Run ingestion (build_vectordb.py) before querying, so there is "
                "a vocabulary to embed queries against."
            )
        return joblib.load(self._vectorizer_path)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embeds a batch of chunk texts.

        Ingestion inserts chunks in fixed-size batches (see
        vector_store.store_chunks_in_batches), which means this method is
        called once per batch, not once for the whole corpus. A TF-IDF
        vectorizer's output dimensionality depends on its fitted
        vocabulary, so re-fitting on every batch would give each batch a
        different vector space and a different dimension - Chroma rejects
        that outright once a collection's dimensionality is set by the
        first batch. So: fit (and persist) only on the very first call;
        every subsequent call in this run - or after a process restart -
        reuses that same fitted vectorizer via `.transform()`.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer

        import joblib

        if self._vectorizer is None:
            if self._vectorizer_path.exists():
                # Re-ingesting into an existing collection: reuse its vocabulary
                # so old and new vectors stay comparable.
                self._vectorizer = self._load_fitted_vectorizer()
            else:
                self._vectorizer = TfidfVectorizer(max_features=self.max_features, stop_words="english")
                self._vectorizer.fit(texts)
                self.persist_dir.mkdir(parents=True, exist_ok=True)
                joblib.dump(self._vectorizer, self._vectorizer_path)
                logger.info(
                    "TF-IDF backend: fitted vocabulary of %d terms on this batch's %d chunk(s); saved to '%s'",
                    len(self._vectorizer.vocabulary_), len(texts), self._vectorizer_path,
                )

        matrix = self._vectorizer.transform(texts)
        return matrix.toarray().tolist()

    def embed_query(self, text: str) -> List[float]:
        """Transforms a query using the vectorizer fitted at ingestion time
        (loaded from disk if this is a fresh process)."""
        if self._vectorizer is None:
            self._vectorizer = self._load_fitted_vectorizer()
        vector = self._vectorizer.transform([text])
        return vector.toarray()[0].tolist()
