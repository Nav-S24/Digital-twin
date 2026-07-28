"""
Phase 5 OBD Diagnostics Intelligence  –  FastAPI REST API
==========================================================
Endpoints
---------
POST /diagnose          Full diagnostic pipeline
GET  /obd/{code}        Single DTC code lookup
GET  /obd/search?q=     Search knowledge base by keyword
GET  /vehicle/lookup    NHTSA vehicle make/model lookup
GET  /health            Health check
"""

from __future__ import annotations
import os
import sys
import httpx
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Path hack so we can run from any working directory ──
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.orchestrator       import DiagnosticOrchestrator
from services.fault_explanation  import FaultExplanationEngine
from services.obd_knowledge_base import OBDKnowledgeBase

# ── App setup ───────────────────────────────────────────────────────────────
app = FastAPI(
    title       = 'Vehicle Health Intelligence Engine – Phase 5',
    description = 'OBD Diagnostics Intelligence: fault explanations, failure '
                  'probability, remaining useful life, and driver recommendations.',
    version     = '1.0.0',
    docs_url    = '/docs',
    redoc_url   = '/redoc',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# Lazy-loaded singletons (populated in startup event)
_orchestrator: Optional[DiagnosticOrchestrator] = None
_explainer:    Optional[FaultExplanationEngine] = None
_kb:           Optional[OBDKnowledgeBase]       = None

NHTSA_BASE = 'https://vpic.nhtsa.dot.gov/api'


@app.on_event('startup')
async def startup():
    global _orchestrator, _explainer, _kb
    _orchestrator = DiagnosticOrchestrator()
    _explainer    = FaultExplanationEngine()
    _kb           = OBDKnowledgeBase.get()
    print('✅  Phase 5 services loaded.')


# ── Request / Response models ────────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    fault_codes:   list[str]  = Field(default=[], examples=[['P0420', 'P0300']])
    temperature:   float      = Field(default=298.0,  ge=200, le=500,
                                      description='Ambient air temperature in Kelvin')
    rpm:           float      = Field(default=1500.0, ge=0, le=9000,
                                      description='Engine RPM')
    torque:        float      = Field(default=40.0,   ge=0, le=500,
                                      description='Torque in Nm')
    tool_wear:     float      = Field(default=0.0,    ge=0,
                                      description='Accumulated wear proxy (minutes)')
    process_temp:  Optional[float] = Field(default=None,
                                           description='Coolant/process temperature in K')
    vehicle_make:  Optional[str]   = Field(default=None, examples=['Toyota'])
    vehicle_model: Optional[str]   = Field(default=None, examples=['Camry'])
    vehicle_year:  Optional[int]   = Field(default=None, examples=[2020])


class APSSensorRequest(BaseModel):
    """Raw Scania APS sensor packet — any subset of the 170 anonymised
    features (aa_000 ... ee_009). Missing features are imputed with
    training-set medians by the Scania Random Forest model."""
    sensors: dict[str, float] = Field(
        ...,
        description='Mapping of APS sensor name to value',
        examples=[{'aa_000': 52.0, 'ab_000': 0.0, 'ag_001': 1.2}],
    )


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get('/health')
async def health():
    """Quick health-check — confirms all services are loaded."""
    return {
        'status':      'ok',
        'services': {
            'orchestrator':  _orchestrator is not None,
            'knowledge_base': _kb is not None,
            'explainer':      _explainer is not None,
        },
        'obd_codes_loaded': len(_kb.all_codes()) if _kb else 0,
    }


@app.post('/diagnose', summary='Full OBD diagnostic pipeline')
async def diagnose(req: DiagnoseRequest):
    """
    Run the complete Phase-5 diagnostic pipeline:

    1. OBD Knowledge Base lookup for each fault code
    2. AI4I failure-probability prediction
    3. NASA C-MAPSS remaining-useful-life prediction
    4. Scania APS component-risk assessment
    5. Unified recommendation generation

    Returns a rich JSON payload including driver advice, maintenance urgency,
    trip-go/caution/stop status, and optional NHTSA recall URL.
    """
    if _orchestrator is None:
        raise HTTPException(503, 'Services not yet initialised')

    try:
        result = _orchestrator.diagnose(
            fault_codes   = req.fault_codes,
            temperature   = req.temperature,
            rpm           = req.rpm,
            torque        = req.torque,
            tool_wear     = req.tool_wear,
            process_temp  = req.process_temp,
            vehicle_make  = req.vehicle_make,
            vehicle_model = req.vehicle_model,
            vehicle_year  = req.vehicle_year,
        )
        return result
    except Exception as exc:
        raise HTTPException(500, f'Diagnostic pipeline error: {exc}') from exc


@app.get('/obd/search', summary='Search OBD knowledge base')
async def obd_search(
    q:        str = Query(..., min_length=2, description='Search term'),
    max_results: int = Query(default=20, le=100),
):
    """
    Full-text keyword search across code descriptions.

    Example: /obd/search?q=catalyst
    """
    if _kb is None:
        raise HTTPException(503, 'Knowledge base not ready')

    import pandas as pd
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'obd', 'obd_knowledge_base.csv')
    df   = pd.read_csv(path)
    mask = df['description'].str.contains(q, case=False, na=False)
    hits = df[mask].head(max_results)

    return {
        'query':   q,
        'count':   int(len(hits)),
        'results': hits[['code','description','severity','affected_system']].to_dict(orient='records'),
    }


@app.get('/obd/{code}', summary='Single DTC code lookup')
async def obd_lookup(code: str):
    """
    Retrieve full knowledge-base entry for a single OBD DTC code.

    Returns description, severity, affected system, symptoms, impact,
    and recommended action.
    """
    if _explainer is None:
        raise HTTPException(503, 'Knowledge base not ready')
    return _explainer.explain(code.upper())


@app.get('/vehicle/makes', summary='NHTSA vehicle make list')
async def vehicle_makes():
    """Proxy to NHTSA API – returns all passenger-car makes."""
    url = f'{NHTSA_BASE}/vehicles/GetMakesForVehicleType/passenger%20Car?format=json'
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise HTTPException(502, 'NHTSA API unavailable')
    return resp.json()


@app.get('/vehicle/models', summary='NHTSA vehicle models for a make')
async def vehicle_models(make: str = Query(..., examples=['Toyota'])):
    """Proxy to NHTSA API – returns models for a given make."""
    url = f'{NHTSA_BASE}/vehicles/GetModelsForMake/{make}?format=json'
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise HTTPException(502, 'NHTSA API unavailable')
    return resp.json()


@app.get('/vehicle/recalls', summary='NHTSA safety recalls for a vehicle')
async def vehicle_recalls(
    make:  str = Query(..., examples=['Toyota']),
    model: str = Query(..., examples=['Camry']),
    year:  int = Query(..., examples=[2020]),
):
    """
    Query the NHTSA recall database for a specific vehicle.

    Returns any open safety recalls including remedy and risk description.
    """
    url = (f'https://api.nhtsa.gov/recalls/recallsByVehicle'
           f'?make={make}&model={model}&modelYear={year}')
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise HTTPException(502, f'NHTSA recall API returned {resp.status_code}')
    data = resp.json()
    return {
        'make':  make,
        'model': model,
        'year':  year,
        'recall_count': data.get('Count', 0),
        'recalls': data.get('results', []),
    }


@app.post('/diagnose/aps', summary='Full APS sensor-mode component assessment')
async def diagnose_aps(req: APSSensorRequest):
    """
    Run the Scania APS Random Forest model directly on a raw APS sensor
    packet (any subset of the 170 anonymised features: aa_000 ... ee_009).

    Use this endpoint when a truck/vehicle uploads real APS telemetry
    instead of the simplified rpm/temperature/torque inputs used by
    POST /diagnose. Missing features are imputed with training-set
    medians automatically.
    """
    from services.component_failure import ComponentFailureAssessor

    try:
        assessor = ComponentFailureAssessor()
        result = assessor.assess_from_aps_sensors(req.sensors)
        return {
            'mode': 'full_aps_sensor_model',
            'sensors_supplied': len(req.sensors),
            **result,
        }
    except Exception as exc:
        raise HTTPException(500, f'APS sensor assessment error: {exc}') from exc
