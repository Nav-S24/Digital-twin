"""
coaching/coaching_engine.py

Step 6: Generate coaching recommendations from driver score, behaviour
statistics, fuel efficiency, trip summary, and driver profile.

Design:
    - `RuleBasedCoach` ALWAYS runs first and is deterministic, fast,
      and free -- it guarantees the API/dashboard always has coaching
      content even if the LLM is unavailable, rate-limited, or the
      API key is missing.
    - `LLMCoach` (Step 10 integration point) takes the rule-based
      findings and asks an LLM to turn them into a warmer, more
      natural-language coaching narrative. If the LLM call fails for
      any reason, callers transparently fall back to the rule-based
      messages -- coaching output is never empty.
"""

from typing import Dict, List, Optional

from config.settings import PROFILE_LABELS, PROFILES, THRESHOLDS
from utils.exceptions import CoachingGenerationError
from utils.logger import get_logger

logger = get_logger(__name__)


class RuleBasedCoach:
    """Deterministic, template-driven coaching recommendation generator."""

    def __init__(self):
        self._logger = logger

    def generate(self, trip_summary: Dict) -> List[Dict]:
        """
        Args:
            trip_summary: a dict merging trip features + driver_score +
                driver_profile + event counts, e.g. one row of the
                scored/profiled trip table converted with `.to_dict()`,
                plus an `event_counts` sub-dict from
                BehaviorDetector.event_summary().

        Returns:
            List of coaching cards: [{category, message, priority}]
        """
        cards: List[Dict] = []
        events = trip_summary.get("event_counts", {})
        duration_s = max(float(trip_summary.get("trip_duration_s", 0.0) or 0.0), 0.0)
        effective_hours = max(duration_s / 3600.0, 5.0 / 60.0)  # 5-minute floor

        def rate(key: str) -> float:
            return events.get(key, 0) / effective_hours

        # Aggressive acceleration (empirical VED median ~36/hr, 75th ~60/hr)
        accel_rate = rate("aggressive_acceleration")
        if accel_rate > 45:
            context = "city traffic" if trip_summary.get("city_driving_pct", 0) > 50 else "your recent trips"
            cards.append({
                "category": "acceleration",
                "message": f"You accelerate aggressively in {context}. Easing into the throttle "
                           f"reduces wear and improves fuel economy.",
                "priority": "high" if accel_rate > 90 else "medium",
            })

        # Harsh braking (empirical VED median ~15/hr, 75th ~34/hr)
        brake_rate = rate("harsh_braking")
        if brake_rate > 20:
            cards.append({
                "category": "braking",
                "message": "Reduce harsh braking by anticipating traffic and increasing following distance.",
                "priority": "high" if brake_rate > 50 else "medium",
            })

        # Overspeeding (rare in VED; any sustained rate is notable)
        overspeed_rate = rate("overspeeding")
        if overspeed_rate > 5:
            cards.append({
                "category": "speed",
                "message": "You frequently exceed safe speed limits. Maintaining posted limits "
                           "improves both safety and fuel efficiency.",
                "priority": "high" if overspeed_rate > 20 else "medium",
            })

        # Idling
        duration_s = max(float(trip_summary.get("trip_duration_s", 0.0) or 0.0), 1.0)
        idle_ratio = float(trip_summary.get("idle_time_s", 0.0) or 0.0) / duration_s
        if idle_ratio > 0.15:
            cards.append({
                "category": "idling",
                "message": "You spend excessive time idling. Turning off the engine during long "
                           "stops saves fuel and reduces emissions.",
                "priority": "medium",
            })

        # Sharp cornering (empirical VED median ~60/hr, 75th ~92/hr)
        corner_rate = rate("sharp_cornering")
        if corner_rate > 95:
            cards.append({
                "category": "cornering",
                "message": "Sharp cornering detected frequently. Slowing down before turns improves "
                           "vehicle stability and passenger comfort.",
                "priority": "medium",
            })

        # Fuel efficiency
        fuel_eff = trip_summary.get("fuel_efficiency_km_per_l")
        if fuel_eff is not None:
            if fuel_eff >= PROFILES.eco_min_fuel_efficiency_km_per_l:
                cards.append({
                    "category": "fuel_efficiency",
                    "message": "Excellent eco-driving performance -- your fuel efficiency is above average.",
                    "priority": "low",
                })
            elif fuel_eff < PROFILES.eco_min_fuel_efficiency_km_per_l * 0.7:
                cards.append({
                    "category": "fuel_efficiency",
                    "message": "Maintaining a steady 60-90 km/h and avoiding rapid throttle changes "
                               "will noticeably improve your fuel efficiency.",
                    "priority": "medium",
                })

        # Profile-specific closing note
        profile = trip_summary.get("driver_profile")
        if profile == PROFILE_LABELS["SAFE"]:
            cards.append({
                "category": "overall",
                "message": "Great work -- your driving is consistently safe and controlled. Keep it up!",
                "priority": "low",
            })
        elif profile == PROFILE_LABELS["HIGH_RISK"]:
            cards.append({
                "category": "overall",
                "message": "Your recent driving pattern shows elevated risk. Consider reviewing this "
                           "trip's events and focusing on smoother acceleration and braking.",
                "priority": "high",
            })

        if not cards:
            cards.append({
                "category": "overall",
                "message": "No significant risk behaviours detected on this trip. Solid driving!",
                "priority": "low",
            })

        return cards


class CoachingEngine:
    """
    High-level facade combining rule-based coaching with an optional
    LLM narrative layer. This is what the API and dashboard call.
    """

    def __init__(self, llm_coach: Optional["object"] = None):
        self._rule_based = RuleBasedCoach()
        self._llm_coach = llm_coach  # injected LLM client, e.g. coaching.llm_coach.LLMCoach
        self._logger = logger

    def generate_coaching(self, trip_summary: Dict, use_llm: bool = True) -> Dict:
        """
        Returns:
            {
              "cards": [...],                # always populated, rule-based
              "narrative": str | None,        # LLM-generated summary, if available
              "source": "rule_based" | "llm"
            }
        """
        cards = self._rule_based.generate(trip_summary)
        result = {"cards": cards, "narrative": None, "source": "rule_based"}

        if use_llm and self._llm_coach is not None:
            try:
                narrative = self._llm_coach.summarize(trip_summary, cards)
                result["narrative"] = narrative
                result["source"] = "llm"
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("LLM coaching failed, falling back to rule-based cards: %s", exc)

        return result
