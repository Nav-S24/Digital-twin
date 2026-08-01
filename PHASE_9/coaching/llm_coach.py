"""
coaching/llm_coach.py

Step 10: LLM integration for natural-language coaching and reporting.

Uses Google Gemini as the LLM provider.
Every public method degrades gracefully:
if the LLM call fails, it raises CoachingGenerationError and the caller
(CoachingEngine) falls back to rule-based text.
"""

import json
from typing import Dict, List, Optional

from google import genai

from config.settings import LLM
from utils.exceptions import CoachingGenerationError, ConfigurationError
from utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are an expert driving coach and vehicle efficiency analyst working for "
    "Tata Motors' driver analytics platform. You turn structured driving-behaviour "
    "statistics into short, encouraging, specific coaching feedback. You never "
    "invent numbers that were not given to you. You are concise, practical, and "
    "supportive rather than judgmental."
)


class LLMCoach:
    """LLM-powered natural-language coaching and report generation."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or LLM.provider
        self._client = None
        self._logger = logger

    # ------------------------------------------------------------------
    # Client bootstrap
    # ------------------------------------------------------------------

    def _get_client(self):
        if self._client is not None:
            return self._client

        if self.provider != "gemini":
            raise ConfigurationError(
                f"Unsupported LLM provider: {self.provider}"
            )

        if not LLM.google_api_key:
            raise ConfigurationError(
                "GOOGLE_API_KEY is not configured."
            )

        self._client = genai.Client(
            api_key=LLM.google_api_key
        )

        return self._client

    # ------------------------------------------------------------------
    # LLM Call
    # ------------------------------------------------------------------

    def _call_llm(self, user_prompt: str) -> str:
        client = self._get_client()

        try:
            response = client.models.generate_content(
                model=LLM.gemini_model,
                contents=f"{SYSTEM_PROMPT}\n\n{user_prompt}",
            )

            return response.text.strip()

        except Exception as exc:
            raise CoachingGenerationError(
                f"LLM call failed ({self.provider}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_trip_prompt(
        self,
        trip_summary: Dict,
        rule_based_cards: List[Dict],
    ) -> str:

        facts = {
            "driver_score": trip_summary.get("driver_score"),
            "driver_profile": trip_summary.get("driver_profile"),
            "distance_km": round(
                float(
                    trip_summary.get("distance_travelled_km", 0) or 0
                ),
                2,
            ),
            "duration_min": round(
                float(
                    trip_summary.get("trip_duration_s", 0) or 0
                ) / 60,
                1,
            ),
            "avg_speed_kmh": round(
                float(
                    trip_summary.get("avg_speed_kmh", 0) or 0
                ),
                1,
            ),
            "fuel_efficiency_km_per_l": trip_summary.get(
                "fuel_efficiency_km_per_l"
            ),
            "event_counts": trip_summary.get(
                "event_counts",
                {},
            ),
            "highway_pct": round(
                float(
                    trip_summary.get("highway_driving_pct", 0) or 0
                ),
                1,
            ),
            "city_pct": round(
                float(
                    trip_summary.get("city_driving_pct", 0) or 0
                ),
                1,
            ),
            "night_pct": round(
                float(
                    trip_summary.get("night_driving_pct", 0) or 0
                ),
                1,
            ),
        }

        rule_summaries = "\n".join(
            f"- {card['message']}"
            for card in rule_based_cards
        )

        return (
            "Here is one driver's trip data (JSON) and the automated rule-based findings already derived from it:\n\n"
            f"TRIP DATA:\n{json.dumps(facts, indent=2)}\n\n"
            f"RULE-BASED FINDINGS:\n{rule_summaries}\n\n"
            "Write a short (3-5 sentence) coaching narrative for this driver. "
            "Reference the specific numbers where useful. "
            "End with one concrete actionable tip. "
            "Do not repeat the rule-based findings verbatim."
        )

    def _build_report_prompt(
        self,
        period_label: str,
        aggregated_stats: Dict,
    ) -> str:

        return (
            f"Here is a driver's aggregated {period_label} driving statistics (JSON):\n\n"
            f"{json.dumps(aggregated_stats, indent=2, default=str)}\n\n"
            f"Write a {period_label} driving report with these sections:\n"
            "1. Overall Behaviour Summary\n"
            "2. Driving Risks\n"
            "3. Fuel Efficiency\n"
            "4. Safety Recommendations\n"
            "5. Maintenance Suggestions\n\n"
            "Use only the supplied data."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarize(
        self,
        trip_summary: Dict,
        rule_based_cards: List[Dict],
    ) -> str:

        prompt = self._build_trip_prompt(
            trip_summary,
            rule_based_cards,
        )

        return self._call_llm(prompt)

    def generate_report(
        self,
        period_label: str,
        aggregated_stats: Dict,
    ) -> str:

        prompt = self._build_report_prompt(
            period_label,
            aggregated_stats,
        )

        return self._call_llm(prompt)

    def generate_safety_recommendations(
        self,
        driver_profile_summary: Dict,
    ) -> str:

        prompt = (
            "Here is a driver's overall behaviour profile (JSON):\n\n"
            f"{json.dumps(driver_profile_summary, indent=2, default=str)}\n\n"
            "Provide 3 specific, prioritized safety recommendations. "
            "Each recommendation should be one sentence and based only on the supplied data."
        )

        return self._call_llm(prompt)