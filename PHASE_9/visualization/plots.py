"""
visualization/plots.py

Step 9: Plotly visualizations for Driver Behaviour Analytics.

Charts:
    - Speed vs Time
    - Acceleration Timeline
    - Brake Events (on speed/time)
    - Idle Timeline
    - Trip Route (map)
    - Fuel Efficiency Trend
    - Behaviour Distribution
    - Radar Chart (behaviour profile)
    - Score Gauge

Every function returns a `plotly.graph_objects.Figure` so the caller
(Streamlit dashboard or a notebook) decides how/where to render it.
Tata Motors brand colors are used as the default palette.
"""

from typing import Dict, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Tata Motors-inspired brand palette
COLOR_PRIMARY = "#1B3A6B"     # Tata blue
COLOR_ACCENT = "#0072CE"
COLOR_DANGER = "#D32F2F"
COLOR_WARNING = "#F5A623"
COLOR_SUCCESS = "#2E7D32"
COLOR_NEUTRAL = "#8C8C8C"

PROFILE_COLORS = {
    "Safe Driver": COLOR_SUCCESS,
    "Eco Driver": "#00A19A",
    "Normal Driver": COLOR_ACCENT,
    "Aggressive Driver": COLOR_WARNING,
    "High Risk Driver": COLOR_DANGER,
}


def speed_vs_time(kinematics_df: pd.DataFrame, title: str = "Speed vs Time") -> go.Figure:
    """Line chart of vehicle speed (km/h) over the duration of a trip."""
    fig = px.line(
        kinematics_df, x="timestamp", y="speed_kmh", title=title,
        labels={"timestamp": "Time", "speed_kmh": "Speed (km/h)"},
    )
    fig.update_traces(line_color=COLOR_PRIMARY)
    fig.update_layout(template="plotly_white", hovermode="x unified")
    return fig


def acceleration_timeline(kinematics_df: pd.DataFrame, title: str = "Acceleration Timeline") -> go.Figure:
    """Line chart of instantaneous acceleration (m/s^2), color-banded by sign."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=kinematics_df["timestamp"], y=kinematics_df["acceleration_mps2"],
        mode="lines", line=dict(color=COLOR_ACCENT), name="Acceleration",
    ))
    fig.add_hline(y=0, line_color=COLOR_NEUTRAL, line_dash="dot")
    fig.update_layout(
        title=title, xaxis_title="Time", yaxis_title="Acceleration (m/s²)",
        template="plotly_white",
    )
    return fig


def brake_events_chart(kinematics_df: pd.DataFrame, events_df: pd.DataFrame,
                        title: str = "Brake Events") -> go.Figure:
    """Speed-over-time line with harsh-braking events overlaid as markers."""
    fig = speed_vs_time(kinematics_df, title=title)
    brakes = events_df[events_df["event_type"] == "harsh_braking"] if not events_df.empty else events_df
    if brakes is not None and not brakes.empty:
        fig.add_trace(go.Scatter(
            x=brakes["timestamp"], y=brakes["speed_kmh"], mode="markers",
            marker=dict(color=COLOR_DANGER, size=10, symbol="x"),
            name="Harsh Brake",
        ))
    return fig


def idle_timeline(kinematics_df: pd.DataFrame, idle_speed_threshold: float = 1.0,
                   title: str = "Idle Timeline") -> go.Figure:
    """Highlights idle periods (speed ~0) against the speed timeline."""
    fig = speed_vs_time(kinematics_df, title=title)
    idle_points = kinematics_df[kinematics_df["speed_kmh"] <= idle_speed_threshold]
    if not idle_points.empty:
        fig.add_trace(go.Scatter(
            x=idle_points["timestamp"], y=idle_points["speed_kmh"], mode="markers",
            marker=dict(color=COLOR_WARNING, size=6), name="Idle",
        ))
    return fig


def trip_route_map(kinematics_df: pd.DataFrame, title: str = "Trip Route") -> go.Figure:
    """Map view of the GPS trace for a single trip, colored by speed."""
    fig = px.scatter_map(
        kinematics_df, lat="latitude", lon="longitude", color="speed_kmh",
        color_continuous_scale="Bluered", zoom=12, height=500, title=title,
        labels={"speed_kmh": "Speed (km/h)"},
    )
    fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=40, b=0))
    return fig


def fuel_efficiency_trend(trips_df: pd.DataFrame, title: str = "Fuel Efficiency Trend") -> go.Figure:
    """Trend of fuel efficiency (km/L) across trips, ordered chronologically."""
    df = trips_df.dropna(subset=["fuel_efficiency_km_per_l"]).sort_values("trip_start_time")
    fig = px.line(
        df, x="trip_start_time", y="fuel_efficiency_km_per_l", markers=True, title=title,
        labels={"trip_start_time": "Trip Date", "fuel_efficiency_km_per_l": "Fuel Efficiency (km/L)"},
    )
    fig.update_traces(line_color=COLOR_SUCCESS)
    fig.update_layout(template="plotly_white")
    return fig


def behaviour_distribution(event_counts: Dict[str, int], title: str = "Behaviour Distribution") -> go.Figure:
    """Bar chart of detected event counts by type."""
    labels = {
        "aggressive_acceleration": "Aggressive Accel.", "harsh_braking": "Harsh Braking",
        "excessive_idling": "Excessive Idling", "overspeeding": "Overspeeding",
        "rapid_lane_change": "Rapid Lane Change", "sharp_cornering": "Sharp Cornering",
    }
    df = pd.DataFrame({
        "event": [labels.get(k, k) for k in event_counts.keys()],
        "count": list(event_counts.values()),
    }).sort_values("count", ascending=True)
    fig = px.bar(
        df, x="count", y="event", orientation="h", title=title,
        color="count", color_continuous_scale=["#2E7D32", "#F5A623", "#D32F2F"],
    )
    fig.update_layout(template="plotly_white", showlegend=False)
    return fig


def driver_radar_chart(driver_stats: Dict, title: str = "Driver Behaviour Radar") -> go.Figure:
    """
    Radar chart summarizing a driver across 5 normalized (0-100) axes:
    Safety, Smoothness, Fuel Efficiency, Speed Discipline, Low Idling.
    """
    categories = ["Safety", "Smoothness", "Fuel Efficiency", "Speed Discipline", "Low Idling"]
    values = [
        driver_stats.get("safety_score", 50),
        driver_stats.get("smoothness_score", 50),
        driver_stats.get("fuel_efficiency_score", 50),
        driver_stats.get("speed_discipline_score", 50),
        driver_stats.get("low_idling_score", 50),
    ]
    values.append(values[0])
    categories.append(categories[0])

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values, theta=categories, fill="toself",
        line=dict(color=COLOR_ACCENT), name="Driver",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        title=title, template="plotly_white",
    )
    return fig


def score_gauge(score: float, title: str = "Driver Score") -> go.Figure:
    """Gauge chart for the 0-100 driver score with color-banded risk zones."""
    if score >= 85:
        bar_color = COLOR_SUCCESS
    elif score >= 55:
        bar_color = COLOR_ACCENT
    elif score >= 35:
        bar_color = COLOR_WARNING
    else:
        bar_color = COLOR_DANGER

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": title},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": bar_color},
            "steps": [
                {"range": [0, 35], "color": "#FDE8E8"},
                {"range": [35, 55], "color": "#FDF3E0"},
                {"range": [55, 85], "color": "#E3F2FD"},
                {"range": [85, 100], "color": "#E6F4EA"},
            ],
        },
    ))
    fig.update_layout(template="plotly_white", height=300)
    return fig


def build_radar_inputs_from_trip(trip_row: pd.Series) -> Dict:
    """
    Derive the 5 radar-chart sub-scores (0-100) from a single scored
    trip row so `driver_radar_chart` can be called directly off pipeline
    output without the caller hand-computing each axis.
    """
    # Time-based (not distance-based) normalization, matching
    # DriverScorer/DriverProfiler: distance-based rates over-penalize
    # slow, congested driving since less distance accumulates per event
    # at low speed regardless of actual driving quality.
    duration_s = max(float(trip_row.get("trip_duration_s", 0) or 0), 0.0)
    effective_hours = max(duration_s / 3600.0, 5.0 / 60.0)
    risk_events = (
        trip_row.get("num_harsh_brakes", 0) + trip_row.get("num_accelerations", 0)
    )
    risk_rate_per_hour = risk_events / effective_hours
    safety_score = max(0, 100 - risk_rate_per_hour * 0.5)

    accel_std_proxy = abs(trip_row.get("max_acceleration_mps2", 0) - trip_row.get("avg_acceleration_mps2", 0))
    smoothness_score = max(0, 100 - accel_std_proxy * 10)

    fuel_eff = trip_row.get("fuel_efficiency_km_per_l")
    fuel_score = min(100, (fuel_eff or 0) * 5)

    max_speed = trip_row.get("max_speed_kmh", 0) or 1
    avg_speed = trip_row.get("avg_speed_kmh", 0) or 0
    speed_discipline_score = max(0, 100 - abs(max_speed - avg_speed))

    duration = max(float(trip_row.get("trip_duration_s", 0) or 0), 1)
    idle_ratio = float(trip_row.get("idle_time_s", 0) or 0) / duration
    low_idling_score = max(0, 100 - idle_ratio * 200)

    return {
        "safety_score": round(safety_score, 1),
        "smoothness_score": round(smoothness_score, 1),
        "fuel_efficiency_score": round(fuel_score, 1),
        "speed_discipline_score": round(speed_discipline_score, 1),
        "low_idling_score": round(low_idling_score, 1),
    }
