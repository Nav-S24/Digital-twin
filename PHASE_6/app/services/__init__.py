"""
app.services
============
Thin, single-responsibility service modules that wrap external systems:

    embedding_service.py - builds/caches the HuggingFace embedding model
    vector_store.py       - all ChromaDB read/write access
    gemini_service.py     - all Gemini (google-generativeai) API calls
    document_service.py   - PDF loading, chunking, and deduplication

app/ingest.py, app/retriever.py, and app/rag_pipeline.py orchestrate these
services; they should not talk to Chroma, HuggingFace, or Gemini directly.
"""
