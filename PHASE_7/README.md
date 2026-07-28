# Phase 7 — Natural Language Vehicle Assistant

Conversational assistant for the Vehicle Digital Twin project. Adds a `/chat`
endpoint (FastAPI) and a `ChatPanel` React component that plugs into your
existing dashboard.

## Project layout

```
phase7/
├── main.py                     # standalone FastAPI entrypoint (or merge into your own)
├── requirements.txt
├── data/
│   ├── loaders.py               # loads all 4 CSVs once at startup into dict indexes
│   ├── merged_vehicle_state.csv
│   ├── phase5_diagnostic_output.csv
│   ├── obd_knowledge_base.csv
│   └── obd-trouble-codes.csv
├── services/
│   ├── vehicle_service.py       # Vehicle_ID lookup + narrow field views
│   ├── diagnostic_service.py    # OBD extraction + Phase5 -> KB -> raw fallback
│   ├── intent_detector.py       # regex/rule-based intent routing
│   ├── context_builder.py       # builds minimal grounded context per intent
│   ├── llm_service.py           # isolated Anthropic API integration
│   └── chat_orchestrator.py     # coordinates the full flow + session memory
├── routes/
│   └── chat.py                  # POST /chat, POST /chat/clear
└── frontend/
    └── src/components/
        ├── ChatPanel.jsx        # chat UI component
        └── ChatPanel.css
```

## Backend setup

```bash
cd phase7
pip install -r requirements.txt

# Optional but recommended: set your Anthropic API key to get real LLM answers.
# Without it, the assistant runs in DEBUG MODE and returns the raw grounded
# context instead of an LLM-generated answer - useful for verifying retrieval
# logic before spending any LLM calls.
export ANTHROPIC_API_KEY="sk-ant-..."

uvicorn main:app --reload --port 8000
```

If you already have an existing FastAPI app, skip `main.py` and instead add
to your own entrypoint:

```python
from phase7.routes.chat import router as phase7_chat_router
app.include_router(phase7_chat_router)
```

## Postman / curl tests

**Health explanation for a known vehicle:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"vehicle_id": "Vehicle_0042", "session_id": "session_123", "message": "Why is my engine health dropping?"}'
```

**OBD fault diagnosis (no vehicle needed):**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session_124", "message": "What does P0420 mean?"}'
```

**Driving safety with a code:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"vehicle_id": "Vehicle_0002", "session_id": "session_125", "message": "Can I drive with P0101?"}'
```

**Clear a session:**
```bash
curl -X POST http://localhost:8000/chat/clear \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session_123"}'
```

Expected shape for every `/chat` response:
```json
{
  "vehicle_id": "Vehicle_0042",
  "session_id": "session_123",
  "intent": "HEALTH_EXPLANATION",
  "answer": "...",
  "data_sources": ["Merged Vehicle Intelligence"],
  "obd_codes": []
}
```

## Frontend setup

Copy `frontend/src/components/ChatPanel.jsx` and `ChatPanel.css` into your
existing React/Vite dashboard's `src/components/` folder, then render it
wherever your vehicle-selection UI lives:

```jsx
import ChatPanel from "./components/ChatPanel";

function DashboardPage() {
  const [selectedVehicleId, setSelectedVehicleId] = useState("Vehicle_0001");

  return (
    <div className="dashboard-layout">
      {/* ... existing dashboard panels ... */}
      <ChatPanel vehicleId={selectedVehicleId} apiBaseUrl="http://localhost:8000" />
    </div>
  );
}
```

The panel automatically starts a fresh session (clearing prior messages)
whenever `vehicleId` changes, so it can never answer using a stale vehicle's
context.

## Important data notes (validated during Phase 7 design)

- `merged_vehicle_state.csv` has **no OBD code column** — only a numeric
  `fault_count`. There is currently no stored "active fault code" per
  vehicle anywhere in the data. As required, this assistant **never**
  invents or auto-assigns an OBD code to a vehicle — `FAULT_DIAGNOSIS` and
  the OBD-code branch of `DRIVING_SAFETY` only fire when the user types a
  code directly in chat.
- `phase5_diagnostic_output.csv`'s `maintenance_urgency` is `null` for
  ~8,030 of 11,935 codes — these are all `severity=Low` / `failure_risk=Low`
  / `trip_status=OK` codes where an urgency tier was intentionally never
  assigned (not missing data). `ContextBuilder` passes these through as-is;
  the LLM system prompt instructs it to say when a field is unavailable
  rather than guess.
- `obd-trouble-codes.csv` has **no header row** — `data/loaders.py` loads it
  with `header=None` since row 0 (`P0100`) is real data, not a column name.
- NASA C-MAPSS and AI4I raw training data are **not loaded anywhere** in
  this module — only the 4 runtime CSVs listed above are read.
