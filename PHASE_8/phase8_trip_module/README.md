# Phase 8 — Trip Intelligence Module

**Project:** Personalized Vehicle Brain & Health Digital Twin with Natural Language Intelligence

## Update Log — Driver Behaviour, Service Centre, Alternate Routes, Explainable AI

This revision extends the original Phase 8 implementation. **No existing module was
removed or redesigned** — every change below is additive, and all existing
interfaces (`get_route()`, `TripRiskEngine.assess()`, `RecommendationEngine.generate()`,
`TripOrchestrator.assess_trip()`) keep their original signatures and return types.

| File | What changed |
|---|---|
| `config.py` | Added configurable Trip Risk weights (`health_weight`, `failure_weight`, `weather_weight`, `driver_behaviour_weight`, default 40/30/15/15), Driver Behaviour thresholds, an alternate-route risk-score trigger, a critical-component health threshold, and the service-centre data path. |
| `route_engine.py` | **Rewritten routing priority**: OpenRouteService (preferred, geocoding + directions) → OSRM (alternative, unchanged from before) → deterministic mock (offline fallback). `get_route()`'s signature and return shape are unchanged. Added `get_alternate_route()` for alternate-route suggestions. |
| `api/schemas.py` | Additive only: `VehicleState.driver_behaviour_score` (optional), `RouteInfo.is_alternate` (optional, default `False`), and four new schemas — `ServiceCentreRecommendation`, `RecommendationItem`, `ExplanationFactor`, `ExplanationSummary`. `TripResponse` gained four new optional fields (`recommendations_detailed`, `service_centre_recommendation`, `alternate_route`, `alternate_route_reason`, `explanation`) that default to empty/`None`, so existing consumers reading only the original fields are unaffected. |
| `trip_engine.py` | `TripRiskEngine.assess()` now folds Driver Behaviour Score into both the composite risk score (via the configurable weights above) and the GO/CAUTION/NO-GO rules. `TripOrchestrator` now also wires in the new `ServiceCentreEngine` and `ExplainabilityEngine`, and calls `RouteEngine.get_alternate_route()` when warranted. |
| `recommendation_engine.py` | Recommendations are now priority-tagged (Critical/High/Medium/Low) and sorted; added Driver Behaviour-based and critical-component-escalation recommendations. `generate()` keeps its original `List[str]` signature (now sorted by priority); new `generate_detailed()` returns the priority-tagged list. |
| `service_centre_engine.py` | **NEW FILE.** Recommends the nearest Tata Authorized Service Centre from a mocked JSON directory (`data/service_centres.json`), triggered by CAUTION/NO-GO or a critical unhealthy component. |
| `explainability_engine.py` | **NEW FILE.** Builds the "Why this recommendation?" plain-language panel (Vehicle Health / Failure Risk / Weather / Driver Behaviour / Fuel + an overall statement), reusing the same thresholds as the risk engine so it never contradicts the GO/CAUTION/NO-GO badge. |
| `data_loader.py` | Added an optional `driver_behaviour_score` parameter to `get_vehicle_state()` (passthrough only — not part of Phase 3 output). |
| `app.py` | Added optional `driver_behaviour_score` to `QuickTripRequest`. No endpoint signatures removed or renamed. |
| `dashboard.py` | Added a Driver Behaviour Score slider; recommendations panel now groups by priority; added three new panels — Service Centre Recommendation, Alternate Route Suggestion, and "Why this recommendation?" (Explainable AI). |
| `data/service_centres.json` | **NEW FILE.** Mock Tata Authorized Service Centre directory (name, address, lat/lon, contact) — swappable for a real locator API later without touching `service_centre_engine.py`'s public interface. |
| `tests/test_trip_engine.py` | Added regression tests for driver behaviour risk, configurable weights, prioritized recommendations, service centre triggering, and alternate route triggering. |

Phase 8 answers one question: **"Is this vehicle ready for this specific trip, right now?"**
It does this by combining outputs already produced by Phases 2–6 with live/mocked
trip context (route, weather, fuel prices) and applying a transparent, configurable
rule engine to reach a **GO / CAUTION / NO-GO** decision, plus recommendations and
a natural-language summary.

Phase 8 **does not retrain or re-run any ML model**. It only *consumes* what earlier
phases already produced.

---

## 1. How Phase 8 integrates with Phases 1–7

| Phase | What it produced | How Phase 8 uses it |
|---|---|---|
| Phase 1 — Data Collection | Raw datasets (AI4I, NASA C-MAPSS, Scania APS, VED) | Not accessed directly; already baked into Phase 2/3 outputs |
| Phase 2 — Vehicle Health Intelligence Engine | `vehicle_health_score`, per-component health | Fed into `VehicleState.vehicle_health_score`, `engine_health`, `battery_health`, etc. |
| Phase 3 — Predictive Maintenance & Failure Prediction | `Failure_Probability`, `Remaining_Useful_Life_KM` (see `Phase3_Predictions.csv`) | Loaded via `data_loader.VehicleDataLoader`, feeds the Trip Risk Engine |
| Phase 4 — Digital Twin | Component status (engine/battery/brakes = OK/Warning/Fault) | `VehicleState.digital_twin_status`; a "Fault"/"Critical" status forces NO-GO |
| Phase 5 — OBD Diagnostics Intelligence | Active DTC codes, recommendations, severity (see `phase5_diagnostic_output.csv`) | `VehicleState.active_dtc_codes`, `pending_maintenance`; surfaced in Recommendation Engine |
| Phase 6 — Vehicle Knowledge Base (RAG) | Natural-language answers about vehicle systems | Not directly called by Phase 8, but the `llm_engine.py` module follows the same "LLM + fallback" pattern established in Phase 6/7 |
| Phase 7 — Natural Language Vehicle Assistant | Conversational interface | Phase 8's LLM Explanation panel produces the trip-specific natural-language summary; could be exposed as a tool inside the Phase 7 assistant |

`data_loader.py` is the integration seam: point `config.Settings.phase3_predictions_csv`
and `phase5_diagnostic_csv` at your real Phase 3/5 output files (defaults already
point at `data/Phase3_Predictions.csv` and `data/phase5_diagnostic_output.csv`,
copied from your uploads) and Phase 8 will pull real per-vehicle health data
automatically — no retraining, no duplicated logic.

---

## 2. Architecture

```
Previous Phases (AI4I, NASA, Scania, VED) ──► Phase 2/3/4/5/6 outputs
                                                     │
                                                     ▼
                                          data_loader.py (integration)
                                                     │
                                                     ▼
                                          api/schemas.py (VehicleState)
                                                     │
                     ┌───────────────────────────────┼───────────────────────────────┐
                     ▼                               ▼                               ▼
             route_engine.py                 weather_engine.py                fuel_engine.py
          (OSM/OSRM + mock fallback)     (OpenWeatherMap + mock fallback)  (fuel price API + mock)
                     │                               │                               │
                     └───────────────────────────────┼───────────────────────────────┘
                                                     ▼
                                            trip_engine.py
                                   ┌─────────────────┴──────────────────┐
                                   │   TripRiskEngine (configurable      │
                                   │   GO/CAUTION/NO-GO rule engine)     │
                                   └─────────────────┬──────────────────┘
                                                     ▼
                              recommendation_engine.py + llm_engine.py
                                                     │
                                                     ▼
                                   TripResponse ──► app.py (FastAPI) / dashboard.py (Streamlit)
```

---

## 3. Module reference

| File | Responsibility |
|---|---|
| `config.py` | Central settings + `RiskThresholds` (configurable rule engine thresholds, **including composite risk weights**) via pydantic-settings |
| `utils.py` | Logging setup, haversine distance, safe casting, currency/percent formatting |
| `api/schemas.py` | Pydantic contracts: `VehicleState` (**+ driver_behaviour_score**), `TripRequest`, `RouteInfo` (**+ is_alternate**), `WeatherInfo`, `FuelEstimate`, `RiskAssessment`, `TripResponse` (**+ recommendations_detailed, service_centre_recommendation, alternate_route, explanation**), and new `ServiceCentreRecommendation` / `RecommendationItem` / `ExplanationSummary` schemas |
| `route_engine.py` | **Preferred: OpenRouteService** (geocoding + directions). **Alternative: OSRM** (OpenStreetMap, no key needed). Deterministic mock as final fallback. `get_route()` interface unchanged; new `get_alternate_route()` for alternate-route suggestions. |
| `weather_engine.py` | Fetches current weather for source/destination (OpenWeatherMap) and computes a 0–100 **Weather Risk Score**. Deterministic mock fallback otherwise. |
| `fuel_engine.py` | Computes fuel required, cost, and refueling stops needed from distance, mileage, fuel level, and (live/mock) fuel price. |
| `trip_engine.py` | `TripRiskEngine` (configurable GO/CAUTION/NO-GO rules **+ Driver Behaviour Risk**, full trace) + `TripOrchestrator` (wires every engine together, **including the new Service Centre, Alternate Route, and Explainability steps**) |
| `recommendation_engine.py` | Rule-based, **priority-tagged** (Critical/High/Medium/Low) action items — tyres, brakes, DTCs, weather, fuel, traffic, fatigue, **driver behaviour, and critical-component service-centre escalation** |
| `llm_engine.py` | Natural-language trip summary. Uses Claude API if `ANTHROPIC_API_KEY` is set; otherwise a deterministic template generator |
| `service_centre_engine.py` | **NEW.** Recommends the nearest Tata Authorized Service Centre from a mocked JSON directory, triggered by CAUTION/NO-GO or a critical unhealthy component |
| `explainability_engine.py` | **NEW.** Builds the "Why this recommendation?" plain-language explanation panel |
| `data_loader.py` | Loads Phase 3 (`Phase3_Predictions.csv`) and Phase 5 (`phase5_diagnostic_output.csv`) outputs into `VehicleState` objects (**+ optional driver_behaviour_score passthrough**) |
| `app.py` | FastAPI REST service (**+ optional driver_behaviour_score on the quick-trip endpoint**) |
| `dashboard.py` | Streamlit interactive dashboard (**+ Driver Behaviour slider, prioritized recommendations, Service Centre panel, Alternate Route panel, Explainable AI panel**) |

---

## 4. Trip Risk Engine — rule logic

All thresholds AND weights live in `config.RiskThresholds` and can be overridden via
environment variables (see `.env.example`) without touching code.

### Composite Trip Risk score (0–100, higher = riskier)

```
Trip Risk = health_weight   × (100 − Vehicle Health)
          + failure_weight  × (Failure Probability × 100)
          + weather_weight  × Weather Risk Score
          + driver_behaviour_weight × (100 − Driver Behaviour Score)
```
Defaults: `health_weight=0.40`, `failure_weight=0.30`, `weather_weight=0.15`,
`driver_behaviour_weight=0.15` — fully configurable via
`RISK_HEALTH_WEIGHT` / `RISK_FAILURE_WEIGHT` / `RISK_WEATHER_WEIGHT` /
`RISK_DRIVER_BEHAVIOUR_WEIGHT`. A small additive penalty is layered on top for
binary flags not part of the weighted formula: insufficient fuel logistics (+20),
a critical digital-twin fault (+15) or warning (+7), and active OBD fault codes (+10).

**Driver Behaviour Score** (0–100, higher = safer driving) is derived from
telematics — harsh braking, aggressive acceleration, excessive idling,
overspeeding. If not supplied, it defaults to `settings.default_driver_behaviour_score`
(90 — "assumed good") so existing callers that don't send it are unaffected.

### GO / CAUTION / NO-GO rules

**NO-GO** if any of:
- Vehicle health < `health_caution_min` (default 60)
- Failure probability > `failure_caution_max` (default 45%)
- Remaining useful life < `rul_caution_min_km` (default 150 km)
- Digital twin reports a Fault/Critical component
- Fuel shortfall needs more than 2 refueling stops
- Weather risk score > `weather_caution_max` (default 65) — severe weather escalation
- **Driver Behaviour Score < `driver_behaviour_caution_min` (default 50) — NEW**

**CAUTION** if none of the above but any of:
- Vehicle health < `health_go_min` (default 80)
- Failure probability > `failure_go_max` (default 20%)
- Weather risk score > `weather_go_max` (default 30)
- RUL < `rul_go_min_km` (default 500 km)
- Fuel requires at least one refueling stop
- Any active OBD fault code
- **Driver Behaviour Score < `driver_behaviour_go_min` (default 75) — NEW**

**GO** otherwise.

### NEW: Service Centre Recommendation trigger

Independent of the above, the nearest Tata Authorized Service Centre is
recommended whenever trip status is CAUTION/NO-GO **or** any component health
(engine/battery/brake/fuel-system/tyre) falls below
`critical_component_health_threshold` (default 50) **or** the digital twin
reports a Fault/Critical/Failed status — even if the trip itself is still GO.

### NEW: Alternate Route trigger

An alternate route is suggested when weather risk exceeds `weather_caution_max`
(severe weather) **or** the composite risk score exceeds
`alternate_route_risk_score_threshold` (default 55).


---

## 5. Running it

### Install
```bash
pip install -r requirements.txt
```

### FastAPI service
```bash
uvicorn app:app --reload --port 8008
```
- `GET /health` — liveness check
- `GET /vehicles` — lists vehicle IDs available from `data/Phase3_Predictions.csv`
- `POST /trip/assess` — full request using an explicit `VehicleState` (see `data/sample_trip_request.json`)
- `POST /trip/assess/by_vehicle_id` — convenience endpoint; supply `vehicle_id`, `source`, `destination`, fuel info, and Phase 8 pulls health/failure/DTC data automatically

Example:
```bash
curl -X POST http://localhost:8008/trip/assess \
  -H "Content-Type: application/json" \
  -d @data/sample_trip_request.json
```

### Streamlit dashboard
```bash
streamlit run dashboard.py
```
Provides: Vehicle Health Card, Trip Summary, Route info, Weather Card, Fuel
Estimation, Risk gauge, GO/CAUTION/NO-GO badge, Recommendations panel, and the
LLM Explanation panel — all in one page.

### Tests
```bash
pytest tests/ -v
```

---

## 6. Mock mode / offline operation

Every external dependency (OSM geocoding + OSRM routing, OpenWeatherMap, fuel
price API, Anthropic LLM) has a **deterministic mock fallback**:

- If an API key is missing (`OPENWEATHER_API_KEY`, `FUEL_PRICE_API_KEY`,
  `ANTHROPIC_API_KEY`) the corresponding engine runs in mock mode automatically.
- If a live call fails for any reason (network, rate limit, timeout), the
  engine logs it and transparently falls back to mock data — the pipeline
  never crashes due to an external dependency.
- Mock data is **seeded from the input** (e.g. source+destination, or
  fuel type+region) so repeated calls with the same inputs return the same
  mock values — useful for demos and tests.

This means the entire module runs **fully offline**, with no proprietary
services required, exactly as needed for grading/demo environments.

---

## 7. Sample input/output

See `data/sample_trip_request.json` and `data/sample_trip_response.json`.

Sample scenario (matches the spec):
- Vehicle health 88%, failure probability 12%, fuel 42 L @ 18 km/L, Pune → Mumbai
- Output: `GO`, ~23 L fuel required, cost ≈ ₹2,490 (mock fuel price), low risk score

---

## 8. Extending Phase 8

- **Real routing:** set `ORS_API_KEY` and swap `_osrm_route` for an OpenRouteService
  call in `route_engine.py` if you need traffic-aware ETAs or turn-by-turn geometry.
- **Real fuel prices:** implement `FuelEngine._fetch_live` against your preferred
  regional fuel-price provider.
- **Wire into Phase 7 assistant:** expose `TripOrchestrator.assess_trip` as a tool
  the Phase 7 NL assistant can call when a user asks "Can I drive to Mumbai today?"
- **Persist trip history:** log each `TripResponse` to a database for trend
  analysis (e.g., correlate CAUTION/NO-GO trips with subsequent failures from
  Phase 3 predictions).
