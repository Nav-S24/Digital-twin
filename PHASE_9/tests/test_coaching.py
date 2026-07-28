"""tests/test_coaching.py"""

from coaching.coaching_engine import CoachingEngine, RuleBasedCoach


class TestRuleBasedCoach:
    def setup_method(self):
        self.coach = RuleBasedCoach()

    def test_generate_always_returns_at_least_one_card(self):
        trip_summary = {
            "distance_travelled_km": 10.0, "trip_duration_s": 600, "idle_time_s": 30,
            "fuel_efficiency_km_per_l": 15.0, "driver_profile": "Safe Driver",
            "event_counts": {},
        }
        cards = self.coach.generate(trip_summary)
        assert len(cards) >= 1
        for card in cards:
            assert set(card.keys()) == {"category", "message", "priority"}
            assert card["priority"] in {"high", "medium", "low"}

    def test_high_harsh_brake_rate_produces_braking_card(self):
        trip_summary = {
            "distance_travelled_km": 5.0, "trip_duration_s": 400, "idle_time_s": 10,
            "fuel_efficiency_km_per_l": 12.0, "driver_profile": "Aggressive Driver",
            "event_counts": {"harsh_braking": 5},
        }
        cards = self.coach.generate(trip_summary)
        categories = {c["category"] for c in cards}
        assert "braking" in categories

    def test_excessive_idle_ratio_produces_idling_card(self):
        trip_summary = {
            "distance_travelled_km": 5.0, "trip_duration_s": 1000, "idle_time_s": 300,
            "fuel_efficiency_km_per_l": 10.0, "driver_profile": "Normal Driver",
            "event_counts": {},
        }
        cards = self.coach.generate(trip_summary)
        categories = {c["category"] for c in cards}
        assert "idling" in categories

    def test_good_fuel_efficiency_produces_positive_card(self):
        trip_summary = {
            "distance_travelled_km": 10.0, "trip_duration_s": 600, "idle_time_s": 10,
            "fuel_efficiency_km_per_l": 20.0, "driver_profile": "Eco Driver",
            "event_counts": {},
        }
        cards = self.coach.generate(trip_summary)
        assert any(c["category"] == "fuel_efficiency" for c in cards)


class TestCoachingEngine:
    def test_generate_coaching_without_llm_uses_rule_based(self):
        engine = CoachingEngine(llm_coach=None)
        trip_summary = {
            "distance_travelled_km": 5.0, "trip_duration_s": 400, "idle_time_s": 10,
            "fuel_efficiency_km_per_l": 12.0, "driver_profile": "Normal Driver",
            "event_counts": {},
        }
        result = engine.generate_coaching(trip_summary, use_llm=True)
        assert result["source"] == "rule_based"
        assert result["narrative"] is None
        assert len(result["cards"]) >= 1

    def test_llm_failure_falls_back_gracefully(self):
        class FailingLLM:
            def summarize(self, *args, **kwargs):
                raise RuntimeError("simulated LLM failure")

        engine = CoachingEngine(llm_coach=FailingLLM())
        trip_summary = {
            "distance_travelled_km": 5.0, "trip_duration_s": 400, "idle_time_s": 10,
            "fuel_efficiency_km_per_l": 12.0, "driver_profile": "Normal Driver",
            "event_counts": {},
        }
        result = engine.generate_coaching(trip_summary, use_llm=True)
        assert result["source"] == "rule_based"
        assert result["narrative"] is None
        assert len(result["cards"]) >= 1
