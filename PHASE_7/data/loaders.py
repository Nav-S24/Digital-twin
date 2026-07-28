"""
Phase 7 - Data Loaders

Loads the 4 runtime CSVs ONCE at startup into in-memory indexed dicts.
NASA C-MAPSS / AI4I raw data is NOT loaded here - those were used only
for offline ML training in earlier phases and must never appear in chat.

Indexes:
    VEHICLE_INDEX   : Vehicle_ID -> dict of that vehicle's row
    PHASE5_INDEX     : OBD code   -> dict of that code's Phase 5 row
    KB_INDEX         : OBD code   -> dict of that code's knowledge-base row
    RAW_OBD_INDEX    : OBD code   -> plain-text description (fallback only)
"""

import os
import pandas as pd
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MERGED_VEHICLE_PATH = os.path.join(BASE_DIR, "merged_vehicle_state.csv")
PHASE5_PATH = os.path.join(BASE_DIR, "phase5_diagnostic_output.csv")
KB_PATH = os.path.join(BASE_DIR, "obd_knowledge_base.csv")
RAW_OBD_PATH = os.path.join(BASE_DIR, "obd-trouble-codes.csv")


def _load_vehicle_index() -> dict:
    df = pd.read_csv(MERGED_VEHICLE_PATH)
    df = df.where(pd.notnull(df), None)  # NaN -> None for clean JSON/dict use
    return {row["Vehicle_ID"]: row.to_dict() for _, row in df.iterrows()}


def _load_phase5_index() -> dict:
    df = pd.read_csv(PHASE5_PATH)
    df = df.where(pd.notnull(df), None)
    return {row["code"]: row.to_dict() for _, row in df.iterrows()}


def _load_kb_index() -> dict:
    df = pd.read_csv(KB_PATH)
    df = df.where(pd.notnull(df), None)
    return {row["code"]: row.to_dict() for _, row in df.iterrows()}


def _load_raw_obd_index() -> dict:
    # NOTE: this file has NO header row - row 0 (P0100) is real data.
    df = pd.read_csv(RAW_OBD_PATH, header=None, names=["code", "description"])
    df = df.where(pd.notnull(df), None)
    return {row["code"]: row["description"] for _, row in df.iterrows()}


# Loaded once at module import (i.e. once at app startup)
VEHICLE_INDEX: dict = _load_vehicle_index()
PHASE5_INDEX: dict = _load_phase5_index()
KB_INDEX: dict = _load_kb_index()
RAW_OBD_INDEX: dict = _load_raw_obd_index()


def get_vehicle(vehicle_id: str) -> Optional[dict]:
    return VEHICLE_INDEX.get(vehicle_id)


def get_phase5_code(code: str) -> Optional[dict]:
    return PHASE5_INDEX.get(code)


def get_kb_code(code: str) -> Optional[dict]:
    return KB_INDEX.get(code)


def get_raw_obd_code(code: str) -> Optional[str]:
    return RAW_OBD_INDEX.get(code)


if __name__ == "__main__":
    # Quick sanity check when run directly
    print(f"Vehicles loaded: {len(VEHICLE_INDEX)}")
    print(f"Phase5 codes loaded: {len(PHASE5_INDEX)}")
    print(f"KB codes loaded: {len(KB_INDEX)}")
    print(f"Raw OBD codes loaded: {len(RAW_OBD_INDEX)}")
    print()
    print("Sample vehicle lookup (Vehicle_0001):")
    print(get_vehicle("Vehicle_0001"))
    print()
    print("Sample Phase5 lookup (P0101):")
    print(get_phase5_code("P0101"))
