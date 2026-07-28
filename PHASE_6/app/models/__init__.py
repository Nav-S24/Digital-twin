"""
app.models
==========
Pydantic request/response schemas used by app/api.py. Kept separate from
the endpoint definitions so the API contract can be read, tested, and
reused (e.g. by evaluate_rag.py or a future client SDK) without importing
FastAPI itself.
"""
