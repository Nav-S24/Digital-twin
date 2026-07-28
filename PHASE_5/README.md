# Phase 5 — OBD Diagnostics Intelligence
## Vehicle Health Intelligence Engine

### Overview

Phase 5 converts raw OBD fault codes and live vehicle telemetry into
actionable diagnostics, combining a rule-based knowledge base with three
trained ML models.

---

### Architecture

```
phase5_obd/
├── app.py                          ← FastAPI entry-point  (uvicorn)
├── requirements.txt
│
├── data/
│   ├── obd/obd_knowledge_base.csv  ← 11,935 DTC codes (3 sources merged)
│   ├── ai4i/                       ← AI4I 2020 Predictive Maintenance
│   ├── nasa/                       ← NASA C-MAPSS FD001 turbofan data
│   └── scania/                     ← Scania APS Failure dataset
│
├── models/
│   ├── ai4i_xgb.pkl                ← XGBoost failure classifier  (F1=0.84)
│   ├── ai4i_rf.pkl                 ← Random Forest failure classifier
│   ├── ai4i_features.pkl
│   ├── nasa_rul_xgb.pkl            ← XGBoost RUL regressor  (MAE=11.76)
│   ├── nasa_features.pkl
│   ├── nasa_sensor_cols.pkl
│   ├── scania_rf.pkl               ← Random Forest APS classifier  (F1=0.82)
│   ├── scania_imputer.pkl
│   └── scania_features.pkl
│
├── services/
│   ├── obd_knowledge_base.py       ← 11,935-code DTC lookup (O(1))
│   ├── fault_explanation.py        ← Driver-friendly fault descriptions
│   ├── failure_probability.py      ← AI4I ensemble predictor
│   ├── rul_predictor.py            ← NASA C-MAPSS RUL estimator
│   ├── component_failure.py        ← Scania APS component risk
│   ├── recommendation_engine.py    ← Rule-based recommendation builder
│   └── orchestrator.py             ← Single pipeline entry-point
│
├── api/
│   └── routes.py                   ← FastAPI route definitions
│
├── utils/
│   └── helpers.py                  ← Formatting & unit-conversion helpers
│
├── dashboard/
│   ├── index.html                  ← Static HTML/JS console (calls the API)
│   └── streamlit_app.py            ← Streamlit app (calls services directly)
│
└── notebooks/
    └── phase5_obd_walkthrough.ipynb
```

---

### Installation

```bash
pip install -r requirements.txt
pip install streamlit   # only needed for the Streamlit dashboard
```

---

### Three ways to run this

#### 1. API only (Swagger UI)

```bash
cd phase5_obd
python app.py
```

Open **http://localhost:8000/docs** for the interactive Swagger UI — test every
endpoint directly in the browser, no extra setup needed.

#### 2. HTML Dashboard (production-style console)

The dashboard is a static HTML/JS page that calls the FastAPI backend over
HTTP, so the API must be running first.

```bash
# Terminal 1 — start the API
cd phase5_obd
python app.py

# Terminal 2 — serve the dashboard (any static file server works)
cd phase5_obd/dashboard
python -m http.server 8090
```

Open **http://localhost:8090** in your browser. The dashboard defaults to
`http://localhost:8000` as the API base URL — edit the field at the top
of the page if your API runs elsewhere (CORS is already enabled on the
backend, so cross-origin calls from a different port/host work out of the box).

You can also just double-click `dashboard/index.html` to open it directly
as a `file://` page — it still works as long as the API is running on
`localhost:8000`.

#### 3. Streamlit Dashboard (quick local testing)

The Streamlit app calls the diagnostic services directly in-process —
**no separate API server required**.

```bash
cd phase5_obd
streamlit run dashboard/streamlit_app.py
```

Opens automatically at **http://localhost:8501**. Best for rapid iteration
while developing — adjust sliders, hit Run, see results instantly without
juggling two terminals.

---

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/diagnose` | Full diagnostic pipeline |
| `GET`  | `/obd/{code}` | Single DTC code lookup |
| `GET`  | `/obd/search?q=` | Keyword search across 11k+ codes |
| `GET`  | `/vehicle/makes` | NHTSA vehicle make list |
| `GET`  | `/vehicle/models?make=` | NHTSA vehicle models |
| `GET`  | `/vehicle/recalls?make=&model=&year=` | NHTSA safety recall lookup |
| `GET`  | `/health` | Service health check |

---

### Example Request / Response

```bash
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{"fault_codes":["P0420"],"temperature":298,"rpm":2800,"torque":45}'
```

```json
{
  "fault_codes": ["P0420"],
  "code": "P0420",
  "description": "Catalyst System Efficiency Below Threshold (Bank 1)",
  "severity": "Medium",
  "failure_probability": 0.046,
  "failure_risk": "Low",
  "remaining_life": 39,
  "remaining_life_pct": 31.4,
  "rul_category": "Degraded",
  "component_risk": "Medium",
  "trip_status": "CAUTION",
  "driver_advice": "⚠️  Vehicle can be driven for short distances with caution...",
  "maintenance_urgency": "Soon",
  "estimated_repair_window": "Within 24–48 hours",
  "maintenance_actions": [
    "[P0420 – Medium] Schedule service within 1–2 weeks",
    "[RUL Model] Component wear detected – monitor and plan replacement"
  ]
}
```

---

### Model Performance

| Model | Task | Metric | Score |
|-------|------|--------|-------|
| AI4I XGBoost | Failure classification | Macro F1 | 0.84 |
| AI4I Random Forest | Failure classification | Macro F1 | 0.84 |
| NASA C-MAPSS XGBoost | RUL regression | MAE | 11.76 cycles |
| Scania APS Random Forest | Component failure | Macro F1 | 0.82 |

---

### Datasets Used

1. **OBD Knowledge Base** — merged from `obd-trouble-codes.csv`,
   `dtc-database-main` (SQLite, 18k codes), and `dtcdb-master/generic.csv`
2. **AI4I 2020 Predictive Maintenance** — 10,000 records, 5 sensor features,
   machine-failure binary target
3. **NASA C-MAPSS FD001** — 20,631 training rows, 21 sensors, RUL regression
4. **Scania APS Failure** — 60,000 training rows, 170 anonymised APS features

---

### NHTSA Integration

Recall check URL is auto-generated for any `/diagnose` request that includes
`vehicle_make`, `vehicle_model`, and `vehicle_year`:

```
https://api.nhtsa.gov/recalls/recallsByVehicle?make=TOYOTA&model=CAMRY&modelYear=2019
```

Use `/vehicle/recalls?make=Toyota&model=Camry&year=2019` to fetch recalls inline.

> **Note:** `/vehicle/makes`, `/vehicle/models`, and `/vehicle/recalls` make outbound
> calls to `vpic.nhtsa.dot.gov` and `api.nhtsa.gov`. If running behind a restricted
> network/egress allowlist (sandboxes, locked-down corporate networks), add these
> two hosts to your allowlist. The endpoints work correctly with normal internet access.

---

### Full APS Sensor Mode

For vehicles/fleets with real Scania APS telemetry (170 anonymised features),
bypass the simplified vehicle-parameter heuristic and run the trained
Random Forest model directly:

```bash
curl -X POST http://localhost:8000/diagnose/aps \
  -H "Content-Type: application/json" \
  -d '{"sensors":{"aa_000":2130706,"ag_001":1.2,"ay_000":350,"cn_004":98}}'
```

Any subset of the 170 features may be supplied; missing ones are imputed
with training-set medians.
