# RAG Evaluation Report

_This file is a placeholder. It is regenerated automatically by `evaluate_rag.py`
once PDFs have been ingested via `build_vectordb.py`._

To generate a real report:

```bash
python build_vectordb.py
python evaluate_rag.py
```

Note: if you ran `evaluate_rag.py` with `EMBEDDING_BACKEND=tfidf` (the offline
fallback — see README section 0), expect noticeably weaker recall on
natural-language questions than the numbers above/below would suggest for the
default semantic backend; TF-IDF matches on shared words, not meaning. Re-run
with the default `huggingface` backend once internet access is available for a
representative report.
