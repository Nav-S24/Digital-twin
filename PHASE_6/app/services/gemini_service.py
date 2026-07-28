"""
gemini_service.py
==================
All Gemini (google-generativeai) API access lives here. rag_pipeline.py
builds the prompt and reads the answer; it should never touch the SDK
directly, so retry/timeout/auth behavior stays in exactly one place.
"""

from __future__ import annotations

import time

from app.config import settings
from app.utils import get_logger

logger = get_logger(__name__)

try:
    import google.generativeai as genai
    _GEMINI_AVAILABLE = True
except ImportError:  # pragma: no cover - allows the module to import even without the SDK installed
    genai = None  # type: ignore
    _GEMINI_AVAILABLE = False

_client_configured = False


def _ensure_client_configured() -> None:
    """Configures the Gemini SDK exactly once, using the API key from settings/env — never hardcoded."""
    global _client_configured
    if _client_configured:
        return
    if not _GEMINI_AVAILABLE:
        raise RuntimeError(
            "google-generativeai is not installed. Run `pip install google-generativeai` "
            "to enable LLM generation."
        )
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Add it to your environment or .env file before calling Gemini."
        )
    genai.configure(api_key=settings.google_api_key)
    _client_configured = True


def call_gemini(prompt: str) -> str:
    """
    Calls the Gemini API with retry and timeout handling. Retries only on
    transient failures (network/rate-limit-shaped errors); does not retry
    on clearly permanent failures like an invalid API key, since retrying
    those just wastes time and quota.
    """
    _ensure_client_configured()
    model = genai.GenerativeModel(
        model_name=settings.llm_model,
        generation_config={"temperature": settings.llm_temperature},
    )

    last_error: Exception | None = None
    for attempt in range(1, settings.llm_max_retries + 1):
        call_start = time.perf_counter()
        try:
            response = model.generate_content(
                prompt,
                request_options={"timeout": settings.llm_timeout_seconds},
            )
            text = getattr(response, "text", None)
            if not text:
                raise RuntimeError("Gemini returned an empty response.")
            elapsed_ms = (time.perf_counter() - call_start) * 1000
            logger.info(
                "Gemini response received in %.1f ms (model=%s, attempt=%d)",
                elapsed_ms, settings.llm_model, attempt,
            )
            return text.strip()
        except Exception as exc:  # noqa: BLE001 - broad on purpose, classified below
            last_error = exc
            message = str(exc).lower()
            is_permanent = any(term in message for term in ("api key", "permission", "invalid", "unauthorized"))
            if is_permanent or attempt == settings.llm_max_retries:
                logger.error("Gemini call failed permanently on attempt %d: %s", attempt, exc)
                break
            backoff_seconds = 2 ** (attempt - 1)
            logger.warning(
                "Gemini call failed on attempt %d/%d (%s) — retrying in %ds",
                attempt, settings.llm_max_retries, exc, backoff_seconds,
            )
            time.sleep(backoff_seconds)

    raise RuntimeError(f"Gemini generation failed after retries: {last_error}") from last_error
