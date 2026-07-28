"""
data_loader.py
Phase 8 - Trip Intelligence Module

Integration Layer
------------------
Loads and adapts the *outputs* of earlier phases into a VehicleState object,
so Phase 8 never re-runs or retrains any ML model:

  * Phase 3 predictions CSV  -> Vehicle_Health, Failure_Probability, RUL, etc.
  * Phase 5 diagnostic CSV   -> active DTC codes / affected systems, used to
                                populate `active_dtc_codes` and
                                `pending_maintenance` for a given vehicle.

If the CSVs are not present, sensible defaults / sample data are used so the
module still runs end-to-end (see data/sample_vehicle_state.json).
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from api.schemas import VehicleState
from config import settings
from utils import get_logger, safe_float

logger = get_logger(__name__)


class VehicleDataLoader:
    def __init__(
        self,
        phase3_csv: str = settings.phase3_predictions_csv,
        phase5_csv: str = settings.phase5_diagnostic_csv,
    ):
        self.phase3_csv = phase3_csv
        self.phase5_csv = phase5_csv
        self._phase3_df: Optional[pd.DataFrame] = None
        self._phase5_df: Optional[pd.DataFrame] = None

    def _load_phase3(self) -> Optional[pd.DataFrame]:
        if self._phase3_df is not None:
            return self._phase3_df
        if os.path.exists(self.phase3_csv):
            try:
                self._phase3_df = pd.read_csv(self.phase3_csv)
                logger.info("Loaded Phase 3 predictions from %s (%d rows).",
                            self.phase3_csv, len(self._phase3_df))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load Phase 3 CSV: %s", exc)
                self._phase3_df = None
        return self._phase3_df

    def _load_phase5(self) -> Optional[pd.DataFrame]:
        if self._phase5_df is not None:
            return self._phase5_df
        if os.path.exists(self.phase5_csv):
            try:
                self._phase5_df = pd.read_csv(self.phase5_csv)
                logger.info("Loaded Phase 5 diagnostics from %s (%d rows).",
                            self.phase5_csv, len(self._phase5_df))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load Phase 5 CSV: %s", exc)
                self._phase5_df = None
        return self._phase5_df

    def list_vehicle_ids(self) -> list:
        df = self._load_phase3()
        if df is None or "Vehicle_ID" not in df.columns:
            return []
        return df["Vehicle_ID"].dropna().unique().tolist()

    def get_vehicle_state(
        self,
        vehicle_id: str,
        fuel_level_l: float = 30.0,
        mileage_kmpl: Optional[float] = None,
        tank_capacity_l: Optional[float] = None,
        active_dtc_codes: Optional[list] = None,
        driver_behaviour_score: Optional[float] = None,
    ) -> VehicleState:
        """
        Build a VehicleState by merging Phase 3 (health/failure/RUL) with
        any explicitly supplied fuel/mileage/DTC/driver-behaviour information.

        driver_behaviour_score (NEW): 0-100 telematics-derived score (harsh
        braking, aggressive acceleration, excessive idling, overspeeding).
        Not part of Phase 3 output, so it's supplied by the caller (API
        request / dashboard input). If omitted, trip_engine.py falls back to
        config.settings.default_driver_behaviour_score — existing callers
        that don't pass this argument keep working unchanged.
        """
        df3 = self._load_phase3()
        row = None
        if df3 is not None and "Vehicle_ID" in df3.columns:
            match = df3[df3["Vehicle_ID"] == vehicle_id]
            if not match.empty:
                row = match.iloc[0]

        if row is None:
            logger.warning("Vehicle_ID '%s' not found in Phase 3 data; using defaults.", vehicle_id)
            return VehicleState(
                vehicle_id=vehicle_id,
                vehicle_health_score=75.0,
                failure_probability=0.15,
                remaining_useful_life_km=2000.0,
                fuel_level_l=fuel_level_l,
                fuel_tank_capacity_l=tank_capacity_l or settings.default_fuel_tank_capacity_l,
                mileage_kmpl=mileage_kmpl or settings.default_mileage_kmpl,
                active_dtc_codes=active_dtc_codes or [],
                driver_behaviour_score=driver_behaviour_score,
            )

        digital_twin_status = {
            "engine": "OK" if safe_float(row.get("Engine_Health"), 100) >= 60 else "Warning",
            "battery": "OK" if safe_float(row.get("Battery_Health"), 100) >= 60 else "Warning",
        }

        pending_maintenance = []
        recommended_action = row.get("Recommended_Action")
        if isinstance(recommended_action, str) and recommended_action.strip():
            pending_maintenance.append(recommended_action.strip())

        engine_health_raw = row.get("Engine_Health")
        battery_health_raw = row.get("Battery_Health")

        return VehicleState(
            vehicle_id=vehicle_id,
            vehicle_health_score=safe_float(row.get("Vehicle_Health"), 75.0),
            engine_health=safe_float(engine_health_raw) if pd.notna(engine_health_raw) else None,
            battery_health=safe_float(battery_health_raw) if pd.notna(battery_health_raw) else None,
            failure_probability=safe_float(row.get("Failure_Probability"), 0.15),
            remaining_useful_life_km=safe_float(row.get("Remaining_Useful_Life_KM"), 2000.0),
            digital_twin_status=digital_twin_status,
            active_dtc_codes=active_dtc_codes or [],
            pending_maintenance=pending_maintenance,
            driver_behaviour_score=driver_behaviour_score,
            fuel_level_l=fuel_level_l,
            fuel_tank_capacity_l=tank_capacity_l or settings.default_fuel_tank_capacity_l,
            mileage_kmpl=mileage_kmpl or settings.default_mileage_kmpl,
        )

    def get_dtc_details(self, code: str) -> Optional[dict]:
        """Look up a DTC code's diagnostic detail from the Phase 5 output CSV."""
        df5 = self._load_phase5()
        if df5 is None or "code" not in df5.columns:
            return None
        match = df5[df5["code"] == code]
        if match.empty:
            return None
        return match.iloc[0].to_dict()
