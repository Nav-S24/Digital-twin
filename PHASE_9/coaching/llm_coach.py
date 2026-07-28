"""
coaching/llm_coach.py

Step 10: LLM integration for natural-language coaching and reporting.

Supports both Anthropic (Claude) and OpenAI as configurable providers
(see config.settings.LLMConfig). All prompts are built here so they can
be reviewed/tuned in one place. Every public method degrades gracefully:
if the LLM call fails, it raises CoachingGenerationError and the caller
(CoachingEngine) falls back to rule-based text -- the system NEVER
depends on the LLM being available to function.
"""

import json
from typing import Dict, List, Optional

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
    # Client bootstrap (lazy, so import-time never requires API keys)
    # ------------------------------------------------------------------
    def _get_client(self):
        if self._client is not None:
            return self._client

        if self.provider == "anthropic":
            if not LLM.anthropic_api_key:
                raise ConfigurationError("ANTHROPIC_API_KEY is not configured.")
            import anthropic
            self._client = anthropic.Anthropic(api_key=LLM.anthropic_api_key)
        elif self.provider == "openai":
            if not LLM.openai_api_key:
                raise ConfigurationError("OPENAI_API_KEY is not configured.")
            import openai
            self._client = openai.OpenAI(api_key=LLM.openai_api_key)
        else:
            raise ConfigurationError(f"Unsupported LLM provider: {self.provider}")

        return self._client

    def _call_llm(self, user_prompt: str) -> str:
        client = self._get_client()
        try:
            if self.provider == "anthropic":
                response = client.messages.create(
                    model=LLM.anthropic_model,
                    max_tokens=LLM.max_tokens,
                    temperature=LLM.temperature,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return "".join(block.text for block in response.content if block.type == "text").strip()
            else:
                response = client.chat.completions.create(
                    model=LLM.openai_model,
                    max_tokens=LLM.max_tokens,
                    temperature=LLM.temperature,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                return response.choices[0].message.content.strip()
        except Exception as exc:  # noqa: BLE001
            raise CoachingGenerationError(f"LLM call failed ({self.provider}): {exc}") from exc

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------
    def _build_trip_prompt(self, trip_summary: Dict, rule_based_cards: List[Dict]) -> str:
        facts = {
            "driver_score": trip_summary.get("driver_score"),
            "driver_profile": trip_summary.get("driver_profile"),
            "distance_km": round(float(trip_summary.get("distance_travelled_km", 0) or 0), 2),
            "duration_min": round(float(trip_summary.get("trip_duration_s", 0) or 0) / 60, 1),
            "avg_speed_kmh": round(float(trip_summary.get("avg_speed_kmh", 0) or 0), 1),
            "fuel_efficiency_km_per_l": trip_summary.get("fuel_efficiency_km_per_l"),
            "event_counts": trip_summary.get("event_counts", {}),
            "highway_pct": round(float(trip_summary.get("highway_driving_pct", 0) or 0), 1),
            "city_pct": round(float(trip_summary.get("city_driving_pct", 0) or 0), 1),
            "night_pct": round(float(trip_summary.get("night_driving_pct", 0) or 0), 1),
        }
        rule_summaries = "\n".join(f"- {c['message']}" for c in rule_based_cards)
        return (
            "Here is one driver's trip data (JSON) and the automated rule-based "
            "findings already derived from it:\n\n"
            f"TRIP DATA:\n{json.dumps(facts, indent=2)}\n\n"
            f"RULE-BASED FINDINGS:\n{rule_summaries}\n\n"
            "Write a short (3-5 sentence) coaching narrative for this driver. "
            "Reference the specific numbers where useful. End with one concrete, "
            "actionable tip. Do not repeat all rule-based findings verbatim -- "
            "synthesize them into natural prose."
        )

    def _build_report_prompt(self, period_label: str, aggregated_stats: Dict) -> str:
        return (
            f"Here is a driver's aggregated {period_label} driving statistics (JSON):\n\n"
            f"{json.dumps(aggregated_stats, indent=2, default=str)}\n\n"
            f"Write a {period_label} driving report with these sections, each 1-3 sentences:\n"
            "1. Overall Behaviour Summary\n"
            "2. Driving Risks\n"
            "3. Fuel Efficiency\n"
            "4. Safety Recommendations\n"
            "5. Maintenance Suggestions (based on driving intensity/harshness, "
            "e.g. brake wear from harsh braking frequency, tire wear from sharp "
            "cornering frequency)\n"
            "Use only the data provided. Keep the tone supportive and professional."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def summarize(self, trip_summary: Dict, rule_based_cards: List[Dict]) -> str:
        """Generate a short natural-language coaching narrative for one trip."""
        prompt = self._build_trip_prompt(trip_summary, rule_based_cards)
        return self._call_llm(prompt)

    def generate_report(self, period_label: str, aggregated_stats: Dict) -> str:
        """
        Generate a weekly or monthly report.

        Args:
            period_label: "weekly" or "monthly"
            aggregated_stats: dict of aggregated driver statistics for
                the period (avg score, total distance, event totals,
                fuel efficiency trend, etc.)
        """
        prompt = self._build_report_prompt(period_label, aggregated_stats)
        return self._call_llm(prompt)

    def generate_safety_recommendations(self, driver_profile_summary: Dict) -> str:
        """Standalone safety-focused recommendation, used by GET /driver/coaching."""
        prompt = (
            "Here is a driver's overall behaviour profile (JSON):\n\n"
            f"{json.dumps(driver_profile_summary, indent=2, default=str)}\n\n"
            "Provide 3 specific, prioritized safety recommendations for this driver, "
            "each one sentence, based only on the data given."
        )
        return self._call_llm(prompt)
