"""
preprocessing/data_loader.py

Step 1: Load and clean the VED (Vehicle Energy Dataset).

Responsibilities:
    - Load one or more "VED_*_week.csv" files (or a pre-merged CSV)
    - Handle missing values
    - Remove duplicates
    - Convert the VED's DayNum/Timestamp(ms) encoding into a real
      pandas Timestamp
    - Clean and validate GPS coordinates
    - Segment continuous logs into discrete trips
    - Normalize / clip physically impossible values

The VED raw schema (per the dataset README) is:
    DayNum, VehId, Trip, Timestamp(ms), Latitude[deg], Longitude[deg],
    Vehicle Speed[km/h], MAF[g/sec], Engine RPM[RPM], Absolute Load[%],
    OAT[DegC], Fuel Rate[L/hr], Air Conditioning Power[kW],
    Air Conditioning Power[Watts], Heater Power[Watts],
    HV Battery Current[A], HV Battery SOC[%], HV Battery Voltage[V],
    Short Term Fuel Trim Bank 1[%], Short Term Fuel Trim Bank 2[%],
    Long Term Fuel Trim Bank 1[%], Long Term Fuel Trim Bank 2[%]

DayNum 1 == Nov 1st, 2017 00:00:00 (reference date used to reconstruct
an absolute timestamp from DayNum + Timestamp(ms) which is the
milliseconds elapsed since the start of that trip's logging session).
"""

import glob
import os
from datetime import datetime, timedelta
from typing import List, Optional, Union

import numpy as np
import pandas as pd

from config.settings import PATHS, THRESHOLDS
from utils.exceptions import DataLoadError, DataValidationError
from utils.logger import get_logger

logger = get_logger(__name__)

# VED reference date: DayNum 1 = Nov 1, 2017 00:00:00
VED_REFERENCE_DATE = datetime(2017, 11, 1, 0, 0, 0)

# Rename map: raw VED column -> internal snake_case column
COLUMN_RENAME_MAP = {
    "DayNum": "day_num",
    "VehId": "veh_id",
    "Trip": "trip_id",
    "Timestamp(ms)": "timestamp_ms",
    "Latitude[deg]": "latitude",
    "Longitude[deg]": "longitude",
    "Vehicle Speed[km/h]": "speed_kmh",
    "MAF[g/sec]": "maf_g_s",
    "Engine RPM[RPM]": "engine_rpm",
    "Absolute Load[%]": "absolute_load_pct",
    "OAT[DegC]": "outside_air_temp_c",
    "Fuel Rate[L/hr]": "fuel_rate_l_hr",
    "Air Conditioning Power[kW]": "ac_power_kw",
    "Air Conditioning Power[Watts]": "ac_power_w",
    "Heater Power[Watts]": "heater_power_w",
    "HV Battery Current[A]": "hv_battery_current_a",
    "HV Battery SOC[%]": "hv_battery_soc_pct",
    "HV Battery Voltage[V]": "hv_battery_voltage_v",
    "Short Term Fuel Trim Bank 1[%]": "stft_bank1_pct",
    "Short Term Fuel Trim Bank 2[%]": "stft_bank2_pct",
    "Long Term Fuel Trim Bank 1[%]": "ltft_bank1_pct",
    "Long Term Fuel Trim Bank 2[%]": "ltft_bank2_pct",
}

REQUIRED_COLUMNS = [
    "day_num", "veh_id", "trip_id", "timestamp_ms",
    "latitude", "longitude", "speed_kmh",
]


class VEDDataLoader:
    """Loads, cleans, and segments raw VED driving logs."""

    def __init__(self, raw_data_dir: Optional[str] = None):
        self.raw_data_dir = raw_data_dir or PATHS.raw_data_dir
        self._logger = logger

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def discover_files(self, pattern: str = "VED_*week.csv") -> List[str]:
        """Find all weekly VED CSV files in the raw data directory."""
        search_path = os.path.join(self.raw_data_dir, pattern)
        files = sorted(glob.glob(search_path))
        if not files:
            self._logger.warning("No files matched pattern '%s' in %s", pattern, self.raw_data_dir)
        return files

    def load_csv(self, filepath: str) -> pd.DataFrame:
        """
        Load a single VED CSV file and rename columns to snake_case.

        Raises:
            DataLoadError: if the file cannot be read or is missing
                required columns.
        """
        if not os.path.exists(filepath):
            raise DataLoadError(f"File not found: {filepath}")

        try:
            df = pd.read_csv(filepath, low_memory=False)
        except Exception as exc:  # noqa: BLE001 - surface as DataLoadError
            raise DataLoadError(f"Failed to read CSV '{filepath}': {exc}") from exc

        df = df.rename(columns=COLUMN_RENAME_MAP)

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise DataLoadError(
                f"File '{filepath}' is missing required columns: {missing}"
            )

        self._logger.info("Loaded %d rows from %s", len(df), os.path.basename(filepath))
        return df

    def load_multiple(self, filepaths: List[str]) -> pd.DataFrame:
        """Load and concatenate multiple VED CSV files into one DataFrame."""
        if not filepaths:
            raise DataLoadError("No filepaths provided to load_multiple().")

        frames = [self.load_csv(fp) for fp in filepaths]
        combined = pd.concat(frames, ignore_index=True)
        self._logger.info("Combined %d files into %d total rows", len(filepaths), len(combined))
        return combined

    def load(self, source: Union[str, List[str]]) -> pd.DataFrame:
        """
        Flexible entry point.

        Args:
            source: a single CSV path, a directory containing VED CSVs,
                or a list of CSV paths.
        """
        if isinstance(source, list):
            return self.load_multiple(source)
        if os.path.isdir(source):
            files = self.discover_files_in(source)
            return self.load_multiple(files)
        return self.load_csv(source)

    def discover_files_in(self, directory: str, pattern: str = "*.csv") -> List[str]:
        files = sorted(glob.glob(os.path.join(directory, pattern)))
        if not files:
            raise DataLoadError(f"No CSV files found in directory: {directory}")
        return files

    # ------------------------------------------------------------------
    # Cleaning
    # ------------------------------------------------------------------
    def handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Handle missing values.

        Strategy:
            - Rows missing core signals (veh_id, trip_id, timestamp_ms,
              latitude, longitude, speed_kmh) are dropped, since a
              driving-behaviour row is meaningless without them.
            - Sensor columns that are frequently NaN for a given vehicle
              type (e.g. HV battery fields on gasoline cars, fuel-rate
              fields on EVs) are forward/backward filled *within each
              trip* and otherwise left as NaN (handled downstream by
              feature engineering, which is signal-aware).
        """
        before = len(df)
        df = df.dropna(subset=REQUIRED_COLUMNS)
        dropped_core = before - len(df)
        if dropped_core:
            self._logger.info("Dropped %d rows missing core columns", dropped_core)

        optional_cols = [c for c in df.columns if c not in REQUIRED_COLUMNS]
        if optional_cols and "trip_id" in df.columns and "veh_id" in df.columns:
            df[optional_cols] = (
                df.groupby(["veh_id", "trip_id"], group_keys=False)[optional_cols]
                .apply(lambda g: g.ffill().bfill())
            )

        return df.reset_index(drop=True)

    def remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove exact duplicate rows and duplicate (veh_id, trip_id, timestamp_ms) keys."""
        before = len(df)
        df = df.drop_duplicates()
        df = df.drop_duplicates(subset=["veh_id", "trip_id", "timestamp_ms"], keep="first")
        removed = before - len(df)
        if removed:
            self._logger.info("Removed %d duplicate rows", removed)
        return df.reset_index(drop=True)

    def convert_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert VED's DayNum + Timestamp(ms) encoding into an absolute
        pandas Timestamp column `timestamp`.

        DayNum is a fractional day count where DayNum 1 == Nov 1, 2017
        00:00:00. Timestamp(ms) is the elapsed milliseconds since the
        start of that particular trip's log, so the absolute time for
        each row is:

            absolute_time = reference_date
                             + (day_num - 1) days
                             + timestamp_ms milliseconds
        """
        day_offset = pd.to_timedelta(df["day_num"] - 1, unit="D")
        ms_offset = pd.to_timedelta(df["timestamp_ms"], unit="ms")
        df["timestamp"] = pd.Timestamp(VED_REFERENCE_DATE) + day_offset + ms_offset
        df["hour_of_day"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.dayofweek  # 0 = Monday
        return df

    def clean_gps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate and clean GPS coordinates.

        - Drops rows with latitude/longitude outside plausible bounds
          for the VED collection area (continental US bounding box, a
          loose sanity check that also catches sentinel values like 0,0).
        - Removes rows that imply an impossible instantaneous jump
          speed between consecutive GPS fixes for the same trip
          (GPS glitches).
        """
        before = len(df)
        df = df[
            df["latitude"].between(24.0, 50.0) & df["longitude"].between(-125.0, -66.0)
        ]
        dropped_bounds = before - len(df)
        if dropped_bounds:
            self._logger.info("Dropped %d rows with implausible GPS coordinates", dropped_bounds)

        df = df.sort_values(["veh_id", "trip_id", "timestamp"]).reset_index(drop=True)
        df = self._remove_gps_speed_jumps(df)
        return df

    def _remove_gps_speed_jumps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag and drop points implying > gps_jump_speed_kmh between fixes."""
        before = len(df)
        grouped = df.groupby(["veh_id", "trip_id"], sort=False)

        lat_prev = grouped["latitude"].shift(1)
        lon_prev = grouped["longitude"].shift(1)
        dt_seconds = grouped["timestamp"].diff().dt.total_seconds().replace(0, np.nan)

        dist_km = _haversine_km(lat_prev, lon_prev, df["latitude"], df["longitude"])
        implied_speed = (dist_km / (dt_seconds / 3600.0)).fillna(0)

        keep_mask = implied_speed <= THRESHOLDS.gps_jump_speed_kmh
        df = df[keep_mask]
        removed = before - len(df)
        if removed:
            self._logger.info("Removed %d rows with implausible GPS speed jumps", removed)
        return df.reset_index(drop=True)

    def normalize_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clip / sanitize physically impossible sensor values.

        This is NOT statistical normalization (z-score/min-max) -- that
        is applied later, per-feature, in feature_engineering, since
        scaling should happen on engineered trip-level features, not
        raw time-series points.
        """
        df["speed_kmh"] = df["speed_kmh"].clip(lower=0, upper=250)
        if "engine_rpm" in df.columns:
            df["engine_rpm"] = df["engine_rpm"].clip(lower=0, upper=8000)
        if "fuel_rate_l_hr" in df.columns:
            df["fuel_rate_l_hr"] = df["fuel_rate_l_hr"].clip(lower=0, upper=60)
        if "hv_battery_soc_pct" in df.columns:
            df["hv_battery_soc_pct"] = df["hv_battery_soc_pct"].clip(lower=0, upper=100)
        return df

    # ------------------------------------------------------------------
    # Trip segmentation
    # ------------------------------------------------------------------
    def segment_trips(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Assign a globally unique `global_trip_id` combining veh_id and
        trip_id (VED already segments trips via the `Trip` column, but
        trip numbers reset/repeat across vehicles, so we must qualify
        them). Also drops trips that are too short to analyze reliably.
        """
        df["global_trip_id"] = df["veh_id"].astype(str) + "_" + df["trip_id"].astype(str)

        counts = df.groupby("global_trip_id")["global_trip_id"].transform("count")
        before_trips = df["global_trip_id"].nunique()
        df = df[counts >= THRESHOLDS.min_trip_points].reset_index(drop=True)
        after_trips = df["global_trip_id"].nunique()
        dropped = before_trips - after_trips
        if dropped:
            self._logger.info(
                "Dropped %d trips with fewer than %d points",
                dropped, THRESHOLDS.min_trip_points,
            )
        return df

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    def run_pipeline(self, source: Union[str, List[str]]) -> pd.DataFrame:
        """
        Execute the full Step 1 pipeline:
        load -> missing values -> duplicates -> timestamps -> GPS
        cleaning -> normalization -> trip segmentation.
        """
        self._logger.info("Starting VED preprocessing pipeline")
        df = self.load(source)
        self._validate_schema(df)

        df = self.handle_missing_values(df)
        df = self.remove_duplicates(df)
        df = self.convert_timestamps(df)
        df = self.clean_gps(df)
        df = self.normalize_values(df)
        df = self.segment_trips(df)

        self._logger.info(
            "Preprocessing complete: %d rows, %d vehicles, %d trips",
            len(df), df["veh_id"].nunique(), df["global_trip_id"].nunique(),
        )
        return df

    def _validate_schema(self, df: pd.DataFrame) -> None:
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise DataValidationError(f"Loaded data is missing required columns: {missing}")
        if df.empty:
            raise DataValidationError("Loaded data is empty after column validation.")


def _haversine_km(
    lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series
) -> pd.Series:
    """Vectorized haversine distance (km) between two sets of lat/lon points."""
    r = 6371.0088
    lat1r, lon1r, lat2r, lon2r = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    c = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return pd.Series(r * c, index=lat1.index if hasattr(lat1, "index") else None)
