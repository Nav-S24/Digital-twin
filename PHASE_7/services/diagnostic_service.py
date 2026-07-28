"""
Phase 7 - DiagnosticService

Handles everything OBD-code related:
  * Regex extraction of OBD-II codes from free text (P/B/C/U + 4 digits)
  * Lookup chain: Phase 5 (primary) -> OBD Knowledge Base (secondary) -> Raw OBD list (fallback)

Phase 5 is keyed by `code`, NEVER by Vehicle_ID. This service never
assigns a code to a vehicle on its own - it only looks up codes that
were either explicitly typed by the user in chat, or (in a future
phase) supplied by an upstream system that actually stores an active
fault code per vehicle. merged_vehicle_state.csv currently has no such
column, so today every lookup here is user-code-driven.
"""

import re
from typing import Optional

from data.loaders import get_phase5_code, get_kb_code, get_raw_obd_code

OBD_CODE_PATTERN = re.compile(r"\b([PBCU]0?[0-9A-F]{3,4})\b", re.IGNORECASE)


class DiagnosticService:

    @staticmethod
    def extract_codes(text: str) -> list[str]:
        """Extract and normalize OBD-II style codes from free text."""
        if not text:
            return []
        raw_matches = OBD_CODE_PATTERN.findall(text)
        normalized = []
        for m in raw_matches:
            code = m.upper()
            # Normalize to standard P/B/C/U + 4-digit form where possible
            if len(code) == 4:
                code = code[0] + "0" + code[1:]
            normalized.append(code)
        # de-dupe, preserve order
        seen = set()
        result = []
        for c in normalized:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return result

    @staticmethod
    def lookup(code: str) -> dict:
        """
        Search order: Phase 5 -> OBD Knowledge Base -> Raw OBD fallback.
        Returns a dict: {"code": ..., "source": ..., "data": {...} or None}
        source is one of:
            "Phase 5 Diagnostic Store"
            "OBD Knowledge Base"
            "OBD Fallback Reference"
            "NOT_FOUND"
        """
        code = code.upper()

        p5 = get_phase5_code(code)
        if p5 is not None:
            return {"code": code, "source": "Phase 5 Diagnostic Store", "data": p5}

        kb = get_kb_code(code)
        if kb is not None:
            return {"code": code, "source": "OBD Knowledge Base", "data": kb}

        raw = get_raw_obd_code(code)
        if raw is not None:
            return {
                "code": code,
                "source": "OBD Fallback Reference",
                "data": {"code": code, "description": raw},
            }

        return {"code": code, "source": "NOT_FOUND", "data": None}

    @staticmethod
    def lookup_many(codes: list[str]) -> list[dict]:
        return [DiagnosticService.lookup(c) for c in codes]
