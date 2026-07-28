"""
dashboard.py
Phase 8 - Trip Intelligence Module

Streamlit dashboard providing an interactive Trip Readiness Assessment UI:
  - Vehicle Health Card
  - Trip Summary
  - Route Map
  - Weather Card
  - Fuel Estimation
  - Risk Indicators
  - GO / CAUTION / NO-GO Badge
  - Recommendations Panel (NEW: grouped by Critical/High/Medium/Low priority)
  - NEW: Service Centre Recommendation panel (shown for CAUTION/NO-GO or a
    critical unhealthy component)
  - NEW: Alternate Route Suggestion panel (shown for severe weather or high
    composite risk)
  - NEW: "Why this recommendation?" Explainable AI panel
  - LLM Explanation Panel

CHANGE LOG (this revision): added a Driver Behaviour Score input in the
sidebar, and the four new panels listed above. No existing panel was
removed or restructured.

Run with:
    streamlit run dashboard.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api.schemas import TripRequest, VehicleState
from data_loader import VehicleDataLoader
from trip_engine import TripOrchestrator

st.set_page_config(page_title="Trip Intelligence — Phase 8", page_icon="🚗", layout="wide")

STATUS_COLORS = {"GO": "#1DB954", "CAUTION": "#F5A623", "NO-GO": "#E03131"}

orchestrator = TripOrchestrator()
loader = VehicleDataLoader()


# ------------------------------------------------------------------ #
# Sidebar — inputs
# ------------------------------------------------------------------ #
st.sidebar.title("🚗 Trip Intelligence")
st.sidebar.caption("Phase 8 — Trip Readiness Assessment")

vehicle_ids = loader.list_vehicle_ids()
use_existing = st.sidebar.checkbox("Load vehicle from Phase 3 output", value=bool(vehicle_ids))

if use_existing and vehicle_ids:
    vehicle_id = st.sidebar.selectbox("Vehicle ID", vehicle_ids)
else:
    vehicle_id = st.sidebar.text_input("Vehicle ID", value="Vehicle_0001")

st.sidebar.markdown("---")
source = st.sidebar.text_input("Source", value="Pune")
destination = st.sidebar.text_input("Destination", value="Mumbai")

st.sidebar.markdown("---")
fuel_level = st.sidebar.number_input("Current Fuel Level (L)", min_value=0.0, value=42.0, step=1.0)
tank_capacity = st.sidebar.number_input("Tank Capacity (L)", min_value=1.0, value=45.0, step=1.0)
mileage = st.sidebar.number_input("Mileage (km/L)", min_value=1.0, value=18.0, step=0.5)
fuel_type = st.sidebar.selectbox("Fuel Type", ["petrol", "diesel", "cng"])

dtc_input = st.sidebar.text_input("Active DTC codes (comma-separated, optional)", value="")
active_dtc_codes = [c.strip() for c in dtc_input.split(",") if c.strip()]

st.sidebar.markdown("---")
driver_behaviour_score = st.sidebar.slider(
    "Driver Behaviour Score (0-100, higher = safer)",
    min_value=0, max_value=100, value=90,
    help="Derived from telematics: harsh braking, aggressive acceleration, "
         "excessive idling, overspeeding. 100 = ideal driving behaviour.",
)

run_button = st.sidebar.button("🔍 Assess Trip Readiness", type="primary", use_container_width=True)


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #
st.title("Trip Readiness Assessment")
st.caption("Combines Vehicle Health (Phase 2), Failure Prediction (Phase 3), Digital Twin (Phase 4), "
           "Maintenance/DTC status (Phase 5-6), route, weather, and fuel economics.")

if run_button:
    with st.spinner("Assessing trip readiness..."):
        vehicle = loader.get_vehicle_state(
            vehicle_id=vehicle_id,
            fuel_level_l=fuel_level,
            mileage_kmpl=mileage,
            tank_capacity_l=tank_capacity,
            active_dtc_codes=active_dtc_codes,
            driver_behaviour_score=float(driver_behaviour_score),
        )
        request = TripRequest(
            vehicle=vehicle, source=source, destination=destination, fuel_type=fuel_type
        )
        result = orchestrator.assess_trip(request)

    # --- GO/CAUTION/NO-GO badge ---
    color = STATUS_COLORS.get(result.risk.trip_status, "#888")
    st.markdown(
        f"""
        <div style="background-color:{color}22;border:2px solid {color};
                    border-radius:12px;padding:16px;text-align:center;margin-bottom:20px;">
            <span style="font-size:28px;font-weight:800;color:{color};">
                {result.risk.trip_status}
            </span>
            <div style="font-size:14px;color:#555;">Risk Score: {result.risk.risk_score}/100</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    # --- Vehicle Health Card ---
    with col1:
        st.subheader("🩺 Vehicle Health")
        st.metric("Overall Health Score", f"{vehicle.vehicle_health_score:.1f}%")
        st.metric("Failure Probability", f"{vehicle.failure_probability*100:.1f}%")
        st.metric("Driver Behaviour Score", f"{driver_behaviour_score}/100")
        if vehicle.remaining_useful_life_km:
            st.metric("Remaining Useful Life", f"{vehicle.remaining_useful_life_km:.0f} km")
        if vehicle.digital_twin_status:
            st.write("**Digital Twin Status**")
            for comp, status in vehicle.digital_twin_status.items():
                st.write(f"- {comp.capitalize()}: `{status}`")
        if vehicle.active_dtc_codes:
            st.write("**Active DTC Codes**: " + ", ".join(vehicle.active_dtc_codes))

    # --- Trip Summary + Route ---
    with col2:
        st.subheader("🗺️ Trip Summary")
        st.write(f"**{source} → {destination}**")
        st.metric("Distance", f"{result.route.distance_km} km")
        st.metric("Est. Travel Time", f"{result.route.duration_min:.0f} min")
        if result.route.elevation_gain_m:
            st.write(f"Elevation gain: {result.route.elevation_gain_m:.0f} m")
        if result.route.traffic_level:
            st.write(f"Traffic: {result.route.traffic_level}")
        st.caption(f"Route data source: {result.route.source_mode}")

    # --- Weather Card ---
    with col3:
        st.subheader("🌦️ Weather")
        st.metric("Condition", result.weather.condition)
        st.metric("Temperature", f"{result.weather.temperature_c:.1f}°C")
        st.write(f"Rain: {result.weather.rain_mm} mm | Wind: {result.weather.wind_kph} kph "
                 f"| Humidity: {result.weather.humidity_pct}%")
        if result.weather.alerts:
            st.error("⚠️ " + "; ".join(result.weather.alerts))
        st.caption(f"Weather Risk Score: {result.weather.weather_risk_score}/100 "
                    f"(source: {result.weather.source_mode})")

    st.markdown("---")

    col4, col5 = st.columns([1, 1])

    # --- Fuel Estimation ---
    with col4:
        st.subheader("⛽ Fuel Estimation")
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("Fuel Required", f"{result.fuel.fuel_required_l} L")
        fc2.metric("Fuel Available", f"{result.fuel.fuel_available_l} L")
        fc3.metric("Est. Cost", f"₹{result.fuel.fuel_cost:,.0f}")
        if not result.fuel.fuel_sufficient:
            st.warning(f"Refueling stops needed: {result.fuel.refueling_stops_needed}")
        else:
            st.success("Fuel sufficient for the full trip.")
        st.caption(f"Price per litre: ₹{result.fuel.price_per_litre} "
                    f"(source: {result.fuel.source_mode})")

    # --- Risk Indicators ---
    with col5:
        st.subheader("📊 Risk Indicators")
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=result.risk.risk_score,
            title={"text": "Composite Trip Risk"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 35], "color": "#d3f9d8"},
                    {"range": [35, 65], "color": "#ffe8cc"},
                    {"range": [65, 100], "color": "#ffc9c9"},
                ],
            },
        ))
        fig.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    col6, col7 = st.columns([1, 1])

    # --- Recommendations Panel (NEW: grouped by priority) ---
    with col6:
        st.subheader("✅ Recommendations")
        priority_styles = {
            "Critical": ("🔴", "#E03131"),
            "High": ("🟠", "#F5A623"),
            "Medium": ("🟡", "#F2C037"),
            "Low": ("🟢", "#1DB954"),
        }
        grouped = {"Critical": [], "High": [], "Medium": [], "Low": []}
        for item in result.recommendations_detailed:
            grouped.setdefault(item.priority, []).append(item.text)

        any_shown = False
        for priority in ["Critical", "High", "Medium", "Low"]:
            texts = grouped.get(priority, [])
            if not texts:
                continue
            any_shown = True
            icon, color = priority_styles.get(priority, ("⚪", "#888"))
            st.markdown(f"**{icon} {priority}**")
            for text in texts:
                st.markdown(
                    f"<div style='border-left:3px solid {color};padding-left:8px;margin-bottom:6px;'>{text}</div>",
                    unsafe_allow_html=True,
                )
        if not any_shown:
            st.write("No specific concerns detected. Standard pre-trip checklist recommended.")

    # --- Contributing Factors / Rule Trace ---
    with col7:
        st.subheader("🔎 Contributing Factors")
        for factor in result.risk.contributing_factors:
            st.write(f"- {factor}")
        with st.expander("Rule engine trace (debug)"):
            for line in result.risk.rule_trace:
                st.code(line)

    st.markdown("---")

    # --- NEW: Service Centre Recommendation panel ---
    if result.service_centre_recommendation:
        sc = result.service_centre_recommendation
        st.subheader("🔧 Nearest Tata Authorized Service Centre")
        st.warning(sc.reason)
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Service Centre", sc.name)
        sc2.metric("Distance", f"{sc.distance_km} km")
        sc3.metric("Est. Travel Time", f"{sc.estimated_travel_time_min:.0f} min")
        st.caption(f"{sc.address}" + (f" | 📞 {sc.contact}" if sc.contact else ""))
        st.caption(f"(source: {sc.source_mode} — mocked directory; swappable for a real locator API)")
        st.markdown("---")

    # --- NEW: Alternate Route Suggestion panel ---
    if result.alternate_route:
        st.subheader("🔀 Alternate Route Suggested")
        st.info(result.alternate_route_reason)
        ar1, ar2, ar3 = st.columns(3)
        ar1.metric("Alt. Distance", f"{result.alternate_route.distance_km} km",
                    delta=f"{result.alternate_route.distance_km - result.route.distance_km:+.1f} km vs primary")
        ar2.metric("Alt. Travel Time", f"{result.alternate_route.duration_min:.0f} min")
        if result.alternate_route.traffic_level:
            ar3.metric("Alt. Traffic", result.alternate_route.traffic_level)
        st.caption(f"(source: {result.alternate_route.source_mode})")
        st.markdown("---")

    # --- NEW: Explainable AI panel — "Why this recommendation?" ---
    st.subheader("🧠 Why this recommendation?")
    status_icon = {"Good": "🟢", "Moderate": "🟡", "Poor": "🔴"}
    for factor in result.explanation.factors:
        icon = status_icon.get(factor.status, "⚪")
        st.write(f"{icon} **{factor.label}:** {factor.value}")
    st.markdown(
        f"""
        <div style="background-color:{color}15;border-left:4px solid {color};
                    padding:10px 14px;margin-top:8px;border-radius:6px;">
            <strong>Overall recommendation:</strong> {result.explanation.overall_statement}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # --- LLM Explanation Panel ---
    st.subheader("💬 Trip Summary (Natural Language)")
    st.info(result.natural_language_summary)

else:
    st.info("Configure the trip in the sidebar and click **Assess Trip Readiness** to begin.")
    if vehicle_ids:
        st.write(f"Loaded {len(vehicle_ids)} vehicles from Phase 3 output "
                 f"(`data/Phase3_Predictions.csv`).")
        st.dataframe(pd.DataFrame({"Vehicle_ID": vehicle_ids[:20]}))
