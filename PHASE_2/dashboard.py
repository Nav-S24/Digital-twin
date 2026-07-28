"""
dashboard.py
============
Vehicle Health Intelligence Engine - Health Score Dashboard (Phase 2).

Fills the roadmap deliverable the original notebook-only implementation
never produced: a "Health score dashboard".

Two tabs:
  1. Fleet Overview   - aggregate stats + distributions across Output.csv
  2. Live Scorer      - enter sensor values, get engine/battery/vehicle
                        health scores plus ML health score / RUL, computed
                        by calling directly into the same src/ package the
                        API uses (no network hop required to run standalone).

Run with:
    streamlit run dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import DATA_DIR
from src.health_scoring import add_all_health_scores

st.set_page_config(page_title="Vehicle Health Dashboard", page_icon="🚗", layout="wide")


@st.cache_data(show_spinner="Loading reference fleet...")
def load_fleet() -> pd.DataFrame:
    path = DATA_DIR / "Output.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_resource(show_spinner="Loading trained models...")
def load_models():
    import joblib
    from src.config import CLASSIFIER_MODEL_PATH, REGRESSOR_MODEL_PATH
    clf = joblib.load(CLASSIFIER_MODEL_PATH) if Path(CLASSIFIER_MODEL_PATH).exists() else None
    reg = joblib.load(REGRESSOR_MODEL_PATH) if Path(REGRESSOR_MODEL_PATH).exists() else None
    return clf, reg


def health_color(score: float) -> str:
    if score >= 90:
        return "🟢"
    if score >= 75:
        return "🟡"
    if score >= 60:
        return "🟠"
    return "🔴"


st.title("🚗 Vehicle Health Intelligence Engine")
st.caption("Phase 2 — Health Score Dashboard")

tab_fleet, tab_live = st.tabs(["📊 Fleet Overview", "🧪 Live Scorer"])

# ---------------------------------------------------------------------------
# Tab 1: Fleet Overview
# ---------------------------------------------------------------------------
with tab_fleet:
    df = load_fleet()

    if df.empty:
        st.warning("No reference fleet data found at data/Output.csv.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Vehicles", f"{len(df):,}")
        col2.metric("Avg. Vehicle Health", f"{df['vehicle_health'].mean():.1f}")
        col3.metric("Avg. Engine Health", f"{df['engine_health'].mean():.1f}")
        col4.metric("Failure Rate", f"{df['failure'].mean() * 100:.2f}%")

        st.divider()

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Health Class Distribution")
            counts = df["health_class"].value_counts().reset_index()
            counts.columns = ["health_class", "count"]
            fig = px.pie(
                counts, names="health_class", values="count",
                color="health_class",
                color_discrete_map={"Excellent": "#2ecc71", "Good": "#f1c40f",
                                     "Warning": "#e67e22", "Critical": "#e74c3c"},
                hole=0.4,
            )
            st.plotly_chart(fig, width='stretch')

        with col_b:
            st.subheader("Vehicle Health Distribution")
            fig = px.histogram(df, x="vehicle_health", nbins=30, color_discrete_sequence=["#3498db"])
            fig.update_layout(xaxis_title="Vehicle Health Score", yaxis_title="Count")
            st.plotly_chart(fig, width='stretch')

        st.subheader("Engine vs. Battery Health")
        fig = px.scatter(
            df, x="engine_health", y="battery_health", color="health_class",
            color_discrete_map={"Excellent": "#2ecc71", "Good": "#f1c40f",
                                 "Warning": "#e67e22", "Critical": "#e74c3c"},
            opacity=0.6, hover_data=["trip_readiness", "fault_count"],
        )
        st.plotly_chart(fig, width='stretch')

        st.subheader("Fleet Data Sample")
        st.dataframe(df.head(100), width='stretch')

# ---------------------------------------------------------------------------
# Tab 2: Live Scorer
# ---------------------------------------------------------------------------
with tab_live:
    st.subheader("Score a Live Sensor Reading")
    st.caption("Computes engine/battery/vehicle health with the same rule-based "
               "engine as the API, plus ML health score & RUL if trained models are available.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Engine sensors**")
        temperature = st.slider("Temperature (°C)", 30.0, 140.0, 85.0)
        pressure = st.slider("Pressure (PSI)", 5.0, 50.0, 28.0)
        rpm = st.slider("RPM", 0.0, 7000.0, 2800.0)
        vibration = st.slider("Vibration (g)", 0.0, 2.0, 0.3)
        fault_count = st.slider("Active fault codes", 0, 15, 1)

    with col2:
        st.markdown("**Battery sensors**")
        battery_voltage = st.slider("Battery voltage (V)", 9.0, 14.0, 12.4)
        battery_current = st.slider("Battery current draw (A)", 0.0, 150.0, 40.0)
        battery_temp = st.slider("Battery temperature (°C)", 0.0, 80.0, 30.0)

    if st.button("Compute Health Score", type="primary"):
        reading = pd.DataFrame([{
            "temperature": temperature, "pressure": pressure, "rpm": rpm,
            "vibration": vibration, "battery_voltage": battery_voltage,
            "battery_current": battery_current, "battery_temp": battery_temp,
            "fault_count": fault_count,
        }])
        scored = add_all_health_scores(reading)
        row = scored.iloc[0]

        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{health_color(row['engine_health'])} Engine Health", f"{row['engine_health']:.1f}")
        m2.metric(f"{health_color(row['battery_health'])} Battery Health", f"{row['battery_health']:.1f}")
        m3.metric(f"{health_color(row['vehicle_health'])} Vehicle Health", f"{row['vehicle_health']:.1f}")

        st.info(f"**Health class:** {row['health_class']}  |  "
                f"**Trip readiness:** {row['trip_readiness']:.1f} ({row['trip_readiness_label']})")

        clf, reg = load_models()
        if clf is not None:
            from src.train_classifier import get_feature_columns
            feature_cols = get_feature_columns(scored)
            proba_failure = clf.predict_proba(scored[feature_cols].values)[:, 1][0]
            ml_score = 100 * (1 - proba_failure)
            st.metric("ML Health Score", f"{ml_score:.1f}",
                      help="100 = low predicted failure risk, from the trained XGBoost classifier.")
        else:
            st.caption("ML health score unavailable — no trained classifier found. Run `python train_models.py` first.")

        if reg is not None:
            from src.train_classifier import _EXCLUDE
            from src.train_regressor import prepare_rul_target
            rul_ready = prepare_rul_target(scored)
            rul_exclude = _EXCLUDE | {"RUL", "RUL_synthetic"}
            feature_cols = [c for c in rul_ready.select_dtypes(include="number").columns if c not in rul_exclude]
            predicted_rul = reg.predict(rul_ready[feature_cols].values)[0]
            st.metric("Predicted Remaining Useful Life", f"{predicted_rul:.1f} cycles")
        else:
            st.caption("RUL estimate unavailable — no trained regressor found. Run `python train_models.py` first.")
