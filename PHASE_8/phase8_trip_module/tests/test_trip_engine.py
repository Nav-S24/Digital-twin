"""
tests/test_trip_engine.py
Basic smoke + rule-engine tests for Phase 8 - Trip Intelligence Module.

Run with:
    pytest tests/ -v
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.schemas import FuelEstimate, RouteInfo, TripRequest, VehicleState, WeatherInfo  # noqa: E402
from trip_engine import TripOrchestrator, TripRiskEngine  # noqa: E402


def make_vehicle(**overrides) -> VehicleState:
    base = dict(
        vehicle_id="TEST_001",
        vehicle_health_score=88.0,
        engine_health=90.0,
        battery_health=85.0,
        failure_probability=0.10,
        remaining_useful_life_km=3000.0,
        digital_twin_status={"engine": "OK", "battery": "OK"},
        active_dtc_codes=[],
        pending_maintenance=[],
        fuel_level_l=40.0,
        fuel_tank_capacity_l=45.0,
        mileage_kmpl=18.0,
    )
    base.update(overrides)
    return VehicleState(**base)


def make_route(distance_km=200, traffic="Light"):
    return RouteInfo(distance_km=distance_km, duration_min=180, elevation_gain_m=50,
                      traffic_level=traffic, coordinates=None, source_mode="mock")


def make_weather(risk=10.0, rain=0.0, condition="Clear"):
    return WeatherInfo(temperature_c=28, rain_mm=rain, humidity_pct=50, wind_kph=10,
                        condition=condition, alerts=[], weather_risk_score=risk, source_mode="mock")


def make_fuel(sufficient=True, required=15.0, available=40.0, stops=0):
    return FuelEstimate(fuel_required_l=required, fuel_available_l=available,
                         fuel_sufficient=sufficient, fuel_cost=1500, refueling_stops_needed=stops,
                         price_per_litre=100, source_mode="mock")


def test_healthy_vehicle_returns_go():
    engine = TripRiskEngine()
    vehicle = make_vehicle()
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status == "GO"


def test_low_health_returns_no_go():
    engine = TripRiskEngine()
    vehicle = make_vehicle(vehicle_health_score=40.0)
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status == "NO-GO"


def test_moderate_health_returns_caution():
    engine = TripRiskEngine()
    vehicle = make_vehicle(vehicle_health_score=70.0)
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status == "CAUTION"


def test_severe_weather_escalates_to_no_go():
    engine = TripRiskEngine()
    vehicle = make_vehicle()
    result = engine.assess(vehicle, make_weather(risk=80.0, rain=35, condition="Thunderstorm"),
                            make_fuel(), make_route())
    assert result.trip_status == "NO-GO"


def test_insufficient_fuel_triggers_caution_or_worse():
    engine = TripRiskEngine()
    vehicle = make_vehicle()
    low_fuel = make_fuel(sufficient=False, required=40.0, available=15.0, stops=1)
    result = engine.assess(vehicle, make_weather(), low_fuel, make_route())
    assert result.trip_status in ("CAUTION", "NO-GO")


def test_digital_twin_warning_is_caution_not_no_go():
    """Regression test: a 'Warning' component status should downgrade to
    CAUTION, not force an immediate NO-GO (only hard faults should do that)."""
    engine = TripRiskEngine()
    vehicle = make_vehicle(vehicle_health_score=75.0, digital_twin_status={"engine": "Warning", "battery": "OK"})
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status == "CAUTION"


def test_digital_twin_critical_fault_is_no_go():
    engine = TripRiskEngine()
    vehicle = make_vehicle(digital_twin_status={"engine": "Fault", "battery": "OK"})
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status == "NO-GO"


def test_active_fault_codes_trigger_caution():
    engine = TripRiskEngine()
    vehicle = make_vehicle(active_dtc_codes=["P0442"])
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status in ("CAUTION", "NO-GO")


# --- NEW: Driver Behaviour Score tests ---------------------------------- #

def test_default_driver_behaviour_score_does_not_change_go():
    """A vehicle with no driver_behaviour_score supplied should default to a
    'good' assumed score and not be penalized into CAUTION/NO-GO."""
    engine = TripRiskEngine()
    vehicle = make_vehicle()  # driver_behaviour_score left as None -> default 90
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status == "GO"


def test_low_driver_behaviour_score_triggers_no_go():
    engine = TripRiskEngine()
    vehicle = make_vehicle(driver_behaviour_score=30.0)  # below driver_behaviour_caution_min (50)
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status == "NO-GO"
    assert any("Driver Behaviour" in f for f in result.contributing_factors)


def test_moderate_driver_behaviour_score_triggers_caution():
    engine = TripRiskEngine()
    vehicle = make_vehicle(driver_behaviour_score=60.0)  # between caution_min(50) and go_min(75)
    result = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    assert result.trip_status == "CAUTION"


def test_risk_score_weights_are_configurable():
    """A change in config weights should visibly shift the composite risk score."""
    from config import risk_thresholds
    engine = TripRiskEngine()
    vehicle = make_vehicle(vehicle_health_score=60.0)  # triggers some health risk

    original_weight = risk_thresholds.health_weight
    try:
        risk_thresholds.health_weight = 0.0
        result_zero_weight = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
        risk_thresholds.health_weight = 0.9
        result_high_weight = engine.assess(vehicle, make_weather(), make_fuel(), make_route())
    finally:
        risk_thresholds.health_weight = original_weight

    assert result_high_weight.risk_score > result_zero_weight.risk_score


# --- NEW: Recommendation Engine priority tests -------------------------- #

def test_recommendation_engine_generate_is_backward_compatible():
    from recommendation_engine import RecommendationEngine
    rec_engine = RecommendationEngine()
    vehicle = make_vehicle()
    recs = rec_engine.generate(vehicle, make_weather(), make_fuel(), make_route())
    assert isinstance(recs, list)
    assert all(isinstance(r, str) for r in recs)


def test_recommendations_are_sorted_by_priority():
    from recommendation_engine import RecommendationEngine
    rec_engine = RecommendationEngine()
    vehicle = make_vehicle(engine_health=30.0)  # below critical threshold -> Critical rec
    detailed = rec_engine.generate_detailed(vehicle, make_weather(), make_fuel(), make_route())
    priorities = [item["priority"] for item in detailed]
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    assert priorities == sorted(priorities, key=lambda p: order[p])
    assert priorities[0] == "Critical"


# --- NEW: Service Centre + Alternate Route orchestration tests ---------- #

def test_service_centre_recommended_for_critical_component():
    orchestrator = TripOrchestrator()
    vehicle = make_vehicle(engine_health=30.0)  # critical component issue, even if health score is decent
    request = TripRequest(vehicle=vehicle, source="Pune", destination="Mumbai")
    response = orchestrator.assess_trip(request)
    assert response.service_centre_recommendation is not None


def test_no_service_centre_recommendation_for_clean_go():
    orchestrator = TripOrchestrator()
    vehicle = make_vehicle()  # all healthy -> should be GO, no critical component
    request = TripRequest(vehicle=vehicle, source="Pune", destination="Mumbai")
    response = orchestrator.assess_trip(request)
    assert response.risk.trip_status == "GO"
    assert response.service_centre_recommendation is None


def test_alternate_route_suggested_for_high_composite_risk():
    orchestrator = TripOrchestrator()
    # Deliberately severe on both health and failure to push the *composite*
    # risk score above alternate_route_risk_score_threshold (not just past
    # the rule-based NO-GO cutoff, which can trigger at a lower composite score).
    vehicle = make_vehicle(vehicle_health_score=10.0, failure_probability=0.9, remaining_useful_life_km=50.0)
    request = TripRequest(vehicle=vehicle, source="Pune", destination="Mumbai")
    response = orchestrator.assess_trip(request)
    assert response.risk.risk_score > 55.0
    assert response.alternate_route is not None
    assert response.alternate_route_reason is not None


def test_alternate_route_suggested_for_severe_weather():
    orchestrator = TripOrchestrator()
    vehicle = make_vehicle()  # otherwise healthy vehicle
    request = TripRequest(vehicle=vehicle, source="Pune", destination="Mumbai")
    # Directly exercise the risk engine + orchestrator helper with severe weather
    severe_weather = make_weather(risk=90.0, rain=40, condition="Thunderstorm")
    route = orchestrator.route_engine.get_route(request.source, request.destination)
    from api.schemas import RouteInfo
    route_info = RouteInfo(**route)
    risk = orchestrator.risk_engine.assess(vehicle, severe_weather, make_fuel(), route_info)
    alt_route, reason = orchestrator._maybe_suggest_alternate_route(risk, severe_weather, request)
    assert alt_route is not None
    assert "weather" in reason.lower()


# --- NEW: Explainability panel tests ------------------------------------ #

def test_explanation_panel_has_five_factors():
    orchestrator = TripOrchestrator()
    vehicle = make_vehicle()
    request = TripRequest(vehicle=vehicle, source="Pune", destination="Mumbai")
    response = orchestrator.assess_trip(request)
    assert response.explanation is not None
    labels = [f.label for f in response.explanation.factors]
    assert labels == ["Vehicle Health", "Failure Risk", "Weather", "Driver Behaviour", "Fuel"]
    assert len(response.explanation.overall_statement) > 0


def test_orchestrator_end_to_end_runs_without_network():
    """Ensures the full pipeline runs offline via mock fallbacks."""
    orchestrator = TripOrchestrator()
    vehicle = make_vehicle()
    request = TripRequest(vehicle=vehicle, source="Pune", destination="Mumbai", fuel_type="petrol")
    response = orchestrator.assess_trip(request)
    assert response.risk.trip_status in ("GO", "CAUTION", "NO-GO")
    assert response.route.distance_km > 0
    assert isinstance(response.natural_language_summary, str) and len(response.natural_language_summary) > 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
