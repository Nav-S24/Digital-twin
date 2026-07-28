"""
dashboard/app.py

Step 8: Streamlit Dashboard for Driver Behaviour Analytics.

Panels:
    - Driver Score Gauge
    - Behaviour Profile Card
    - Aggressive Acceleration Count / Harsh Brake Count / Idle Time / Fuel Efficiency
    - Trip Statistics
    - Weekly / Monthly Trend Charts
    - Coaching Recommendation Cards
    - Plus: Speed/Accel/Brake/Idle timelines, Route map, Radar chart

Run with:
    streamlit run dashboard/app.py
"""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import DASHBOARD  # noqa: E402
from detection.behavior_detector import BehaviorDetector  # noqa: E402
from feature_engineering.feature_extractor import TripFeatureExtractor  # noqa: E402
from pipeline import pipeline  # noqa: E402
from utils.exceptions import DriverBehaviorError  # noqa: E402
import visualization.plots as viz  # noqa: E402

st.set_page_config(
    page_title=DASHBOARD.page_title, page_icon=DASHBOARD.page_icon, layout=DASHBOARD.layout,
)


@st.cache_resource(show_spinner="Processing VED dataset...")
def load_pipeline(source: str, _cache_key: str):
    pipeline.run(source)
    return True


def sidebar_controls():
    st.sidebar.title("🚗 Driver Behaviour Analytics")
    st.sidebar.caption("Tata Motors — Personalized Vehicle Brain & Health Digital Twin")

    default_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw"
    )
    source = st.sidebar.text_input(
        "VED data source (CSV file or directory)",
        value=default_path,
        help="Path to a VED_*week.csv file or a directory containing several.",
    )
    run_clicked = st.sidebar.button("Load / Refresh Data", type="primary")
    return source, run_clicked


def render_top_metrics(veh_id: int):
    stats = pipeline.get_driver_statistics(veh_id)
    profile = pipeline.get_driver_profile(veh_id)
    score = pipeline.get_driver_score(veh_id)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Driver Score", f"{score:.1f}" if score is not None else "N/A")
    col2.metric("Profile", profile.get("profile", "N/A"))
    col3.metric("Aggressive Accel.", stats["total_aggressive_accelerations"])
    col4.metric("Harsh Brakes", stats["total_harsh_brakes"])
    fuel_eff = stats["avg_fuel_efficiency_km_per_l"]
    col5.metric("Fuel Efficiency", f"{fuel_eff:.1f} km/L" if fuel_eff else "N/A")

    return stats, profile, score


def render_score_and_profile(veh_id: int, score, profile):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.plotly_chart(viz.score_gauge(score or 0, title="Overall Driver Score"), use_container_width=True)
    with col2:
        st.markdown("#### Behaviour Profile")
        profile_name = profile.get("profile", "Unknown")
        color = viz.PROFILE_COLORS.get(profile_name, "#8C8C8C")
        st.markdown(
            f"""
            <div style="padding:20px;border-radius:12px;background-color:{color}22;
                        border:1px solid {color};">
                <h3 style="color:{color};margin:0;">{profile_name}</h3>
                <p style="margin:6px 0 0 0;">Trips analyzed: <b>{profile.get('trip_count', 0)}</b></p>
                <p style="margin:2px 0 0 0;">Total distance: <b>{profile.get('total_distance_km', 0):.1f} km</b></p>
                <p style="margin:2px 0 0 0;">Weighted avg score: <b>{profile.get('avg_score', 'N/A')}</b></p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_trip_statistics(veh_id: int):
    st.markdown("#### Trip Statistics")
    trips_df = pipeline.list_driver_trips(veh_id)
    display_cols = [
        "global_trip_id", "trip_start_time", "driver_score", "driver_profile",
        "distance_travelled_km", "avg_speed_kmh", "fuel_efficiency_km_per_l",
        "num_harsh_brakes", "num_accelerations",
    ]
    st.dataframe(trips_df[display_cols].reset_index(drop=True), use_container_width=True)
    return trips_df


def render_trend_charts(trips_df: pd.DataFrame):
    st.markdown("#### Trend Charts")
    trend_df = trips_df.sort_values("trip_start_time").copy()
    trend_df["week"] = trend_df["trip_start_time"].dt.to_period("W").astype(str)
    trend_df["month"] = trend_df["trip_start_time"].dt.to_period("M").astype(str)

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Weekly Trend (avg driver score)")
        weekly = trend_df.groupby("week", as_index=False)["driver_score"].mean()
        st.plotly_chart(
            viz.px.line(weekly, x="week", y="driver_score", markers=True, template="plotly_white"),
            use_container_width=True,
        )
    with col2:
        st.caption("Monthly Trend (avg driver score)")
        monthly = trend_df.groupby("month", as_index=False)["driver_score"].mean()
        st.plotly_chart(
            viz.px.line(monthly, x="month", y="driver_score", markers=True, template="plotly_white"),
            use_container_width=True,
        )

    st.plotly_chart(viz.fuel_efficiency_trend(trips_df), use_container_width=True)


def render_trip_deep_dive(veh_id: int, trips_df: pd.DataFrame):
    st.markdown("#### Trip Deep Dive")
    trip_options = trips_df["global_trip_id"].tolist()
    if not trip_options:
        st.info("No trips available for this driver.")
        return
    selected_trip = st.selectbox("Select a trip", trip_options)

    trip_row = trips_df[trips_df["global_trip_id"] == selected_trip].iloc[0]
    trip_raw = pipeline.raw_df[pipeline.raw_df["global_trip_id"] == selected_trip]
    kdf = TripFeatureExtractor().get_point_level_kinematics(trip_raw)
    trip_events = pipeline.get_trip_events(selected_trip)
    event_counts = BehaviorDetector().event_summary(trip_events)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Speed & Braking", "Acceleration", "Idle Timeline", "Route Map", "Behaviour Radar"]
    )
    with tab1:
        st.plotly_chart(viz.brake_events_chart(kdf, trip_events), use_container_width=True)
    with tab2:
        st.plotly_chart(viz.acceleration_timeline(kdf), use_container_width=True)
    with tab3:
        st.plotly_chart(viz.idle_timeline(kdf), use_container_width=True)
    with tab4:
        st.plotly_chart(viz.trip_route_map(kdf), use_container_width=True)
    with tab5:
        radar_inputs = viz.build_radar_inputs_from_trip(trip_row)
        st.plotly_chart(viz.driver_radar_chart(radar_inputs), use_container_width=True)

    st.plotly_chart(viz.behaviour_distribution(event_counts), use_container_width=True)
    return selected_trip


def render_coaching(veh_id: int, selected_trip: str):
    st.markdown("#### Coaching Recommendations")
    use_llm = st.checkbox("Use LLM-generated narrative (requires API key)", value=False)
    result = pipeline.get_trip_coaching(selected_trip, use_llm=use_llm)

    priority_colors = {"high": "#D32F2F", "medium": "#F5A623", "low": "#2E7D32"}
    for card in result["cards"]:
        color = priority_colors.get(card["priority"], "#8C8C8C")
        st.markdown(
            f"""
            <div style="padding:12px 16px;border-left:4px solid {color};
                        background-color:{color}11;border-radius:6px;margin-bottom:8px;">
                <b style="text-transform:capitalize;">{card['category'].replace('_',' ')}</b>
                <span style="float:right;color:{color};font-size:12px;
                             text-transform:uppercase;">{card['priority']}</span>
                <p style="margin:6px 0 0 0;">{card['message']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if result.get("narrative"):
        st.info(result["narrative"])


def main():
    source, run_clicked = sidebar_controls()

    if run_clicked or pipeline.is_ready():
        if run_clicked:
            load_pipeline.clear()
        try:
            load_pipeline(source, source)
        except DriverBehaviorError as exc:
            st.error(f"Failed to load data: {exc}")
            return
    else:
        st.title(f"{DASHBOARD.page_icon} {DASHBOARD.page_title}")
        st.info("Enter a VED data source in the sidebar and click **Load / Refresh Data** to begin.")
        return

    st.title(f"{DASHBOARD.page_icon} {DASHBOARD.page_title}")

    drivers = sorted(pipeline.scored_trips_df["veh_id"].unique().tolist())
    veh_id = st.selectbox("Select Driver (Vehicle ID)", drivers)

    stats, profile, score = render_top_metrics(veh_id)
    st.divider()
    render_score_and_profile(veh_id, score, profile)
    st.divider()
    trips_df = render_trip_statistics(veh_id)
    st.divider()
    render_trend_charts(trips_df)
    st.divider()
    selected_trip = render_trip_deep_dive(veh_id, trips_df)
    st.divider()
    if selected_trip:
        render_coaching(veh_id, selected_trip)


if __name__ == "__main__":
    main()
