"""
response_models.py
===================
Outbound response payloads for the Vehicle Knowledge Base API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    file_name: str
    category: str
    page: Optional[int] = None
    section_title: Optional[str] = None
    chunk_id: Optional[str] = None
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    confidence: float = Field(..., ge=0.0, le=1.0)


class SearchResultItem(BaseModel):
    text: str
    metadata: dict
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]


class DocumentSummary(BaseModel):
    file_name: str
    category: str
    chunk_count: int


class DocumentsResponse(BaseModel):
    total_documents: int
    documents: list[DocumentSummary]


class HealthResponse(BaseModel):
    status: str
    vector_store_loaded: bool
    chunk_count: int
    detail: Optional[str] = None
