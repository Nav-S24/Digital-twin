"""
Phase 7 - IntentDetector

Rule-based intent detection for obvious cases (fast, deterministic, free).
Falls back to a coarse keyword-scoring approach when no rule matches
confidently. An LLM-classification hook is provided for genuinely
ambiguous messages, but is only invoked as a last resort - most chat
messages should never need it.
"""

import re
from enum import Enum
from services.diagnostic_service import DiagnosticService


class Intent(str, Enum):
    HEALTH_EXPLANATION = "HEALTH_EXPLANATION"
    VEHICLE_STATUS = "VEHICLE_STATUS"
    FAILURE_RISK = "FAILURE_RISK"
    RUL_QUERY = "RUL_QUERY"
    MAINTENANCE_QUERY = "MAINTENANCE_QUERY"
    FAULT_DIAGNOSIS = "FAULT_DIAGNOSIS"
    DRIVING_SAFETY = "DRIVING_SAFETY"
    VEHICLE_KNOWLEDGE = "VEHICLE_KNOWLEDGE"


# Ordered rule table: (intent, keyword patterns). First match wins,
# except FAULT_DIAGNOSIS / DRIVING_SAFETY which are boosted whenever
# an OBD code is present in the message (checked separately below).
_RULES: list[tuple[Intent, list[str]]] = [
    (Intent.RUL_QUERY, [
        r"\brul\b", r"remaining useful life", r"how (much|long).*(life|last)",
        r"useful life left",
    ]),
    (Intent.FAILURE_RISK, [
        r"failure risk", r"risk of failure", r"failure probability",
        r"how risky", r"which sensor.*risk", r"most risk",
    ]),
    (Intent.HEALTH_EXPLANATION, [
        r"health.*(drop|declin|low|bad|worse)", r"why.*health",
        r"engine health", r"battery health", r"vehicle health",
        r"what.*health (score|status)",
    ]),
    (Intent.MAINTENANCE_QUERY, [
        r"maintenance", r"service (soon|due|window|schedule)",
        r"what.*(should|need).*(do|service|maintain)",
        r"next service", r"book.*service",
    ]),
    (Intent.DRIVING_SAFETY, [
        r"can i drive", r"safe to drive", r"is it safe", r"trip readiness",
        r"ok to drive", r"drive with",
    ]),
    (Intent.VEHICLE_STATUS, [
        r"vehicle status", r"current status", r"how is my (car|vehicle)",
        r"trip readiness", r"overall status",
    ]),
    (Intent.VEHICLE_KNOWLEDGE, [
        r"what (is|does)\s", r"explain.*(engine|sensor|obd|battery)(?!.*my)",
        r"how does.*work", r"general(ly)? speaking",
    ]),
]


class IntentDetector:

    @staticmethod
    def detect(message: str) -> Intent:
        text = message.lower().strip()
        codes = DiagnosticService.extract_codes(message)

        # OBD code present + diagnosis-ish language -> FAULT_DIAGNOSIS
        if codes:
            if re.search(r"\b(mean|means|meaning|what is|diagnos|fault|error|code)\b", text):
                return Intent.FAULT_DIAGNOSIS
            if re.search(r"\b(drive|driving|safe)\b", text):
                return Intent.DRIVING_SAFETY
            # A bare code with no other context: still treat as diagnosis request
            return Intent.FAULT_DIAGNOSIS

        for intent, patterns in _RULES:
            for pattern in patterns:
                if re.search(pattern, text):
                    return intent

        # Nothing matched confidently -> treat as general knowledge Q&A.
        # (LLM-classification hook could be inserted here for production
        # use; kept out for now to avoid an extra network call per message.)
        return Intent.VEHICLE_KNOWLEDGE

    @staticmethod
    def extract_obd_codes(message: str) -> list[str]:
        return DiagnosticService.extract_codes(message)
