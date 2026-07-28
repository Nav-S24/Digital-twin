"""
Phase 5 OBD Diagnostics — Streamlit Dashboard
==============================================
Quick local testing UI. Calls the diagnostic services directly
(no need to run the FastAPI server separately).

Run with:
    streamlit run dashboard/streamlit_app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="Phase 5 — OBD Diagnostics",
    page_icon="🔵",
    layout="wide",
)

from services.orchestrator import DiagnosticOrchestrator
from services.obd_knowledge_base import OBDKnowledgeBase


@st.cache_resource
def load_orchestrator():
    return DiagnosticOrchestrator()


@st.cache_resource
def load_kb():
    return OBDKnowledgeBase.get()


orch = load_orchestrator()
kb = load_kb()

# ── Styling ──────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #E8F1FB; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; color: #003B73; }
    section[data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #D8E5F4; }
    .trip-ok      { background: #E3F6EF; border-left: 4px solid #0F8B6C; color: #0F8B6C; padding: 14px; border-radius: 6px; }
    .trip-caution { background: #FCEEDB; border-left: 4px solid #C9740A; color: #C9740A; padding: 14px; border-radius: 6px; }
    .trip-stop    { background: #FBE4E4; border-left: 4px solid #C92A2A; color: #C92A2A; padding: 14px; border-radius: 6px; }
    code { background: #E8F1FB !important; color: #003B73 !important; }
    h1, h2, h3 { color: #003B73 !important; }
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #005EB8, #003B73);
        border: none;
    }
</style>
""", unsafe_allow_html=True)

st.title("🔵 Phase 5 — OBD Diagnostics Console")
st.caption("Tata Motors · Vehicle Health Intelligence Engine · runs all services locally, no API server required")

# ── Sidebar inputs ───────────────────────────────────────────────────
with st.sidebar:
    st.header("Diagnostic Inputs")

    st.subheader("Fault Codes")
    preset = st.selectbox(
        "Quick presets",
        ["Custom", "P0420 (Catalyst)", "P0300 (Misfire)", "P0420 + P0300", "No codes (telemetry only)"],
    )
    preset_map = {
        "P0420 (Catalyst)": ["P0420"],
        "P0300 (Misfire)": ["P0300"],
        "P0420 + P0300": ["P0420", "P0300"],
        "No codes (telemetry only)": [],
    }
    default_codes = ", ".join(preset_map.get(preset, ["P0420"]))

    codes_input = st.text_input(
        "Enter DTC codes (comma-separated)",
        value=default_codes if preset != "Custom" else "P0420",
        help="e.g. P0420, P0300, P0171",
    )
    fault_codes = [c.strip().upper() for c in codes_input.split(",") if c.strip()]

    st.subheader("Live Telemetry")
    rpm = st.slider("Engine RPM", 0, 6000, 1500, step=50)
    proc_temp = st.slider("Process Temperature (K)", 250, 420, 310, step=1)
    st.caption(f"≈ {proc_temp - 273.15:.1f} °C")
    torque = st.slider("Torque (Nm)", 0, 150, 40, step=1)
    tool_wear = st.slider("Tool / Component Wear (min)", 0, 260, 0, step=5)

    st.subheader("Vehicle (optional, for NHTSA recall lookup)")
    col1, col2 = st.columns(2)
    with col1:
        make = st.text_input("Make", placeholder="Toyota")
    with col2:
        model = st.text_input("Model", placeholder="Camry")
    year = st.text_input("Year", placeholder="2020")

    run = st.button("▶ Run Diagnostic", type="primary", use_container_width=True)

# ── Main panel ───────────────────────────────────────────────────────
if run:
    with st.spinner("Running diagnostic pipeline..."):
        result = orch.diagnose(
            fault_codes=fault_codes,
            temperature=proc_temp - 10,
            process_temp=proc_temp,
            rpm=rpm,
            torque=torque,
            tool_wear=tool_wear,
            vehicle_make=make or None,
            vehicle_model=model or None,
            vehicle_year=int(year) if year.strip().isdigit() else None,
        )

    # ── Trip status banner ──
    trip = result['trip_status']
    css_class = {'OK': 'trip-ok', 'CAUTION': 'trip-caution', 'STOP': 'trip-stop'}.get(trip, 'trip-ok')
    icon = {'OK': '🟢', 'CAUTION': '🟡', 'STOP': '🔴'}.get(trip, '⚪')
    st.markdown(
        f'<div class="{css_class}"><b>{icon} TRIP STATUS: {trip}</b> &nbsp;·&nbsp; '
        f"{result['maintenance_urgency']} priority &nbsp;·&nbsp; {result['estimated_repair_window']}</div>",
        unsafe_allow_html=True,
    )
    st.write("")

    # ── Gauge metrics ──
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            "Failure Probability",
            f"{result['failure_probability']:.1%}",
            help="From the AI4I XGBoost + Random Forest ensemble",
        )
        st.caption(f"Risk: **{result['failure_risk']}**")
    with c2:
        st.metric(
            "Remaining Useful Life",
            f"{result['remaining_life']} cycles",
            help="From the NASA C-MAPSS XGBoost regressor",
        )
        st.caption(f"{result['remaining_life_pct']}% · **{result['rul_category']}**")
    with c3:
        st.metric(
            "Component Risk",
            result['component_risk'],
            help="From the Scania APS Random Forest model (heuristic mode)",
        )
        st.caption(f"Severity: **{result['severity']}**")

    st.write("")

    # ── Driver advice ──
    st.subheader("Driver Advice")
    st.info(result['driver_advice'])

    # ── Fault code table ──
    st.subheader(f"Fault Codes ({len(result['fault_codes'])})")
    if result['obd_details']:
        import pandas as pd
        df = pd.DataFrame(result['obd_details'])[['code', 'description', 'severity', 'affected_system']]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("No fault codes supplied — telemetry-only health check.")

    # ── Maintenance actions ──
    st.subheader("Maintenance Actions")
    for action in result['maintenance_actions']:
        st.markdown(f"- {action}")

    # ── Affected components ──
    if result.get('affected_components'):
        st.subheader("Affected Components")
        st.write(", ".join(result['affected_components']))

    # ── NHTSA recall link ──
    if result.get('nhtsa_recall_check_url'):
        st.subheader("NHTSA Recall Check")
        st.markdown(f"[{result['nhtsa_recall_check_url']}]({result['nhtsa_recall_check_url']})")

    # ── Raw JSON (expandable) ──
    with st.expander("Raw diagnostic JSON"):
        st.json(result)

else:
    st.markdown("""
    ### 👈 Configure inputs in the sidebar and click **Run Diagnostic**

    This dashboard calls the Phase 5 services directly — no separate API
    server is required. It wraps:
    - **OBD Knowledge Base** — 11,935 DTC codes
    - **AI4I Failure Probability Model** (XGBoost + Random Forest)
    - **NASA C-MAPSS RUL Model** (XGBoost regressor)
    - **Scania APS Component Risk Model** (Random Forest)
    - **Recommendation Engine**
    """)

    st.subheader("🔍 Quick OBD Code Lookup")
    lookup_code = st.text_input("Look up any DTC code", placeholder="P0420")
    if lookup_code:
        entry = kb.lookup(lookup_code.strip().upper())
        st.json(entry)
