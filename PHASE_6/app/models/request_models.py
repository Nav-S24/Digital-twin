"""
request_models.py
==================
Inbound request payloads for the Vehicle Knowledge Base API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's natural-language question.")
    top_k: int = Field(default=settings.top_k, ge=1, le=20)
    category: Optional[str] = Field(None, description="'manuals' | 'obd_docs' | 'service_guides' | 'maintenance_guides'")

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=settings.top_k, ge=1, le=20)
    category: Optional[str] = None
    search_type: Optional[str] = Field(None, description="'similarity' or 'mmr'")

    @field_validator("query")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()
