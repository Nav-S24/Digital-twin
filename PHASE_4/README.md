# Vehicle Digital Twin Platform — Phase 4

A production-style Vehicle Health Monitoring Digital Twin built on top of Phase 1–3 outputs.

## Architecture

```
vehicle_digital_twin/
├── config/
│   └── settings.py            ← All constants, thresholds, paths
├── data/
│   ├── phase2_output/         ← Output-phase2.csv
│   ├── phase3_output/         ← Phase3_Predictions.csv
│   └── nasa_cmapss/           ← Drop train_FD00x.txt here (optional)
├── twin/
│   ├── engine.py              ← EngineTwin class
│   ├── battery.py             ← BatteryTwin class
│   ├── fuel.py                ← FuelTwin class (derived health)
│   ├── brake.py               ← BrakeTwin class (synthetic estimation)
│   └── vehicle.py             ← VehicleTwin (orchestrates all four)
├── services/
│   ├── data_loader.py         ← Merges Phase 2 + Phase 3 CSVs
│   ├── state_estimator.py     ← Sensor validation & enrichment
│   ├── synchronizer.py        ← Twin registry & update orchestration
│   └── simulation_engine.py   ← Future degradation projection
├── api/
│   └── routes.py              ← FastAPI route handlers
├── dashboard/                 ← React + Vite frontend
│   └── src/
│       ├── pages/             ← 7 dashboard pages
│       ├── components/        ← Reusable UI components
│       ├── hooks/             ← Data-fetching hooks
│       └── utils/             ← API client, helpers
├── main.py                    ← FastAPI application entry point
└── requirements.txt
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- Phase 2 CSV:  `data/phase2_output/Output-phase2.csv`
- Phase 3 CSV:  `data/phase3_output/Phase3_Predictions.csv`

Optional (for CMAPSS-informed engine simulation):
- NASA C-MAPSS files:  `data/nasa_cmapss/train_FD001.txt` (etc.)

## Setup & Run

### 1. Backend (FastAPI)

```bash
# From project root
pip install -r requirements.txt

# Start the API server
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API docs: http://localhost:8000/docs
Health check: http://localhost:8000/digital_twin/health

### 2. Frontend (React)

```bash
cd dashboard
npm install
npm run dev
```

Dashboard: http://localhost:3000

### 3. NASA C-MAPSS (optional, enables physics-informed simulation)

```bash
# Download from https://data.nasa.gov/dataset/CMAPSS-Jet-Engine-Simulated-Data
# Place in:
data/nasa_cmapss/train_FD001.txt
data/nasa_cmapss/train_FD002.txt   # optional
data/nasa_cmapss/train_FD003.txt   # optional
data/nasa_cmapss/train_FD004.txt   # optional
```

The SimulationEngine auto-detects these files at startup. No code change needed.

## API Endpoints

| Method | Endpoint                          | Description                        |
|--------|-----------------------------------|------------------------------------|
| GET    | /digital_twin/health              | API health check                   |
| GET    | /digital_twin/fleet               | Fleet aggregate statistics          |
| GET    | /digital_twin/vehicles            | Paginated vehicle list (filterable) |
| GET    | /digital_twin/ids                 | All vehicle IDs                    |
| GET    | /digital_twin/current/{id}        | Full twin state for one vehicle    |
| GET    | /digital_twin/components/{id}     | All four component states          |
| GET    | /digital_twin/history/{id}        | Historical trend data              |
| GET    | /digital_twin/risk/{id}           | Failure risk digest                |
| GET    | /digital_twin/rul/{id}            | Remaining Useful Life digest       |
| POST   | /digital_twin/simulate            | Run future degradation simulation  |
| GET    | /digital_twin/refresh             | Reload CSV data (hot refresh)      |

### Example: Simulation request

```bash
curl -X POST http://localhost:8000/digital_twin/simulate \
  -H "Content-Type: application/json" \
  -d '{"vehicle_id": "Vehicle_0001", "days": 90}'
```

## Dashboard Pages

| Page              | Route         | Description                                |
|-------------------|---------------|--------------------------------------------|
| Overview          | /             | Health gauges, radar, key metrics          |
| Component Health  | /components   | Per-component cards with gauges and metrics|
| Failure Risk      | /failure      | Risk meter, SHAP explanation, urgency      |
| Simulation        | /simulation   | Future degradation chart, day table        |
| Historical Trends | /history      | Interactive trend charts with brush zoom   |
| Digital Twin      | /twin         | Interactive SVG vehicle diagram            |
| Fleet             | /fleet        | Full 2000-vehicle table, pie/bar charts    |

## Design Decisions

### No model retraining
The Digital Twin is a pure orchestration and simulation layer.
All health scores and predictions come from Phase 2 / Phase 3 outputs.

### Fuel Health algorithm
Derived from engine sensors (temperature, pressure, RPM, vibration, fault count)
with documented weights. See `twin/fuel.py` for full algorithm.

### Brake Health algorithm
Synthetic estimation from mileage proxy (RUL_KM delta), vibration-based
hard-brake detection, and thermal stress. See `twin/brake.py` for full
assumptions and weight rationale.

### Battery SOC/SOH
SOC estimated from terminal voltage via linear OCV–SOC mapping.
SOH proxied from Phase 2 `battery_health`. No NASA Battery Dataset required.

### Database-ready architecture
State is held in memory (dict of VehicleTwin instances). To add PostgreSQL:
1. Replace `get_merged_dataframe()` with a DB query in `data_loader.py`.
2. Add a flush method to `Synchronizer` that writes twin states to the DB.
3. No twin or API code needs to change.
