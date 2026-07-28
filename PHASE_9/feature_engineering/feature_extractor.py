"""
feature_engineering/feature_extractor.py

Step 2: Engineer trip-level features from cleaned VED time-series data.

Produces one row per (veh_id, trip_id) with:
    - Driving features (speed, acceleration, stops, harsh events, ...)
    - Fuel / energy features (consumption, efficiency, eco score)
    - Driving statistics (highway/city/night/peak-hour %)

All feature names are stable, documented column names consumed
downstream by detection, profiling, scoring, and coaching.
"""

from typing import Optional

import numpy as np
import pandas as pd

from config.settings import THRESHOLDS, VEHICLE
from utils.exceptions import FeatureEngineeringError, InsufficientDataError
from utils.logger import get_logger

logger = get_logger(__name__)


class TripFeatureExtractor:
    """Computes point-level kinematics and trip-level aggregate features."""

    def __init__(self):
        self._logger = logger

    # ------------------------------------------------------------------
    # Point-level kinematics (per trip)
    # ------------------------------------------------------------------
    def _compute_point_kinematics(self, trip_df: pd.DataFrame) -> pd.DataFrame:
        """
        Adds per-row kinematic columns to a single trip's DataFrame:
        dt_s, speed_mps, acceleration_mps2, distance_m, heading_deg,
        heading_change_deg_s, lateral_accel_mps2.
        """
        trip_df = trip_df.sort_values("timestamp").reset_index(drop=True)

        trip_df["dt_s"] = trip_df["timestamp"].diff().dt.total_seconds()
        trip_df["dt_s"] = trip_df["dt_s"].fillna(0).clip(lower=0)
        trip_df.loc[trip_df["dt_s"] == 0, "dt_s"] = np.nan  # avoid div-by-zero

        # VED logs at irregular, sub-second intervals. Dividing a raw
        # speed diff by a very small dt hugely amplifies OBD sensor
        # quantization noise into physically implausible "jerk" spikes.
        # A short rolling median smooths that noise while preserving
        # genuine hard-braking / hard-acceleration signatures, which
        # play out over multiple samples, not a single 100ms tick.
        smoothed_speed_kmh = trip_df["speed_kmh"].rolling(window=3, center=True, min_periods=1).median()
        trip_df["speed_mps"] = smoothed_speed_kmh / 3.6

        min_dt_s = 0.4
        raw_accel = trip_df["speed_mps"].diff() / trip_df["dt_s"]
        # Where dt is too small to trust, don't compute a fresh value --
        # forward-fill the last reliable acceleration reading instead.
        trip_df["acceleration_mps2"] = raw_accel.where(trip_df["dt_s"] >= min_dt_s).ffill().fillna(0)
        # clip to physically plausible bounds for a passenger car
        trip_df["acceleration_mps2"] = trip_df["acceleration_mps2"].clip(-8, 8)

        trip_df["distance_m"] = _haversine_m(
            trip_df["latitude"].shift(1), trip_df["longitude"].shift(1),
            trip_df["latitude"], trip_df["longitude"],
        ).fillna(0)

        # GPS bearing is numerically unstable over sub-meter displacements
        # (consumer GPS noise floor is a few meters), which would otherwise
        # register as spurious 180-degree "turns" while nearly stationary
        # or crawling in traffic. Only compute a fresh bearing when the
        # vehicle has actually moved a meaningful distance; otherwise carry
        # the last valid heading forward so heading_change stays near zero.
        min_movement_m = 3.0
        raw_bearing = _bearing_deg(
            trip_df["latitude"].shift(1), trip_df["longitude"].shift(1),
            trip_df["latitude"], trip_df["longitude"],
        )
        raw_bearing = raw_bearing.where(trip_df["distance_m"] >= min_movement_m)
        trip_df["heading_deg"] = raw_bearing.ffill().fillna(0)

        heading_diff = (trip_df["heading_deg"].diff() + 180) % 360 - 180
        trip_df["heading_change_deg_s"] = (heading_diff.abs() / trip_df["dt_s"]).fillna(0)
        # Suppress heading-change readings on rows where the vehicle barely
        # moved between fixes -- no real turn occurred, just GPS jitter.
        trip_df.loc[trip_df["distance_m"] < min_movement_m, "heading_change_deg_s"] = 0.0

        # lateral acceleration approximation: v^2 * (dTheta/dt in rad/s) / v == v * dTheta/dt
        heading_rate_rad_s = np.radians(trip_df["heading_change_deg_s"])
        trip_df["lateral_accel_mps2"] = (trip_df["speed_mps"] * heading_rate_rad_s).clip(0, 10)

        trip_df["dt_s"] = trip_df["dt_s"].fillna(0)
        return trip_df

    # ------------------------------------------------------------------
    # Driving features
    # ------------------------------------------------------------------
    def _driving_features(self, trip_df: pd.DataFrame) -> dict:
        speed = trip_df["speed_kmh"]
        accel = trip_df["acceleration_mps2"]

        accel_events = accel[accel > 0]
        decel_events = accel[accel < 0]

        idle_mask = trip_df["speed_kmh"] <= THRESHOLDS.idle_speed_kmh
        idle_time_s = trip_df.loc[idle_mask, "dt_s"].sum()

        # stop count: contiguous runs where speed drops to ~0 from a non-zero state
        moving = ~idle_mask
        stop_transitions = (moving.astype(int).diff() == -1).sum()

        harsh_brake_mask = accel <= THRESHOLDS.harsh_braking_mps2
        aggressive_accel_mask = accel >= THRESHOLDS.aggressive_acceleration_mps2
        sharp_turn_mask = trip_df["lateral_accel_mps2"] >= THRESHOLDS.sharp_corner_lateral_accel_mps2

        duration_s = trip_df["dt_s"].sum()
        distance_km = trip_df["distance_m"].sum() / 1000.0

        return {
            "avg_speed_kmh": float(speed.mean()) if len(speed) else 0.0,
            "max_speed_kmh": float(speed.max()) if len(speed) else 0.0,
            "min_speed_kmh": float(speed.min()) if len(speed) else 0.0,
            "avg_acceleration_mps2": float(accel_events.mean()) if len(accel_events) else 0.0,
            "max_acceleration_mps2": float(accel_events.max()) if len(accel_events) else 0.0,
            "avg_deceleration_mps2": float(decel_events.mean()) if len(decel_events) else 0.0,
            "max_deceleration_mps2": float(decel_events.min()) if len(decel_events) else 0.0,
            "trip_duration_s": float(duration_s),
            "distance_travelled_km": float(distance_km),
            "idle_time_s": float(idle_time_s),
            "stop_count": int(stop_transitions),
            "num_accelerations": int(aggressive_accel_mask.sum()),
            "num_harsh_brakes": int(harsh_brake_mask.sum()),
            "num_sharp_turns": int(sharp_turn_mask.sum()),
        }

    # ------------------------------------------------------------------
    # Fuel / energy features
    # ------------------------------------------------------------------
    def _fuel_features(self, trip_df: pd.DataFrame, distance_km: float) -> dict:
        if "fuel_rate_l_hr" in trip_df.columns and trip_df["fuel_rate_l_hr"].notna().any():
            fuel_rate = trip_df["fuel_rate_l_hr"].fillna(0)
            fuel_used_l = float((fuel_rate * (trip_df["dt_s"] / 3600.0)).sum())
        elif "maf_g_s" in trip_df.columns and trip_df["maf_g_s"].notna().any():
            # Fallback: estimate fuel mass flow from MAF using stoichiometric AFR
            maf = trip_df["maf_g_s"].fillna(0)
            fuel_g_s = maf / VEHICLE.afr_stoichiometric
            fuel_g = float((fuel_g_s * trip_df["dt_s"]).sum())
            fuel_used_l = (fuel_g / 1000.0) / VEHICLE.fuel_density_kg_per_l
        else:
            fuel_used_l = 0.0

        energy_kwh = 0.0
        if "hv_battery_current_a" in trip_df.columns and "hv_battery_voltage_v" in trip_df.columns:
            current = trip_df["hv_battery_current_a"].fillna(0)
            voltage = trip_df["hv_battery_voltage_v"].fillna(0)
            power_w = current * voltage
            energy_kwh = float((power_w * (trip_df["dt_s"] / 3600.0)).sum() / 1000.0)
            energy_kwh = abs(energy_kwh)

        fuel_efficiency_km_l = (distance_km / fuel_used_l) if fuel_used_l > 0.01 else np.nan
        eco_score = self._eco_driving_score(trip_df)

        return {
            "energy_consumption_kwh": float(energy_kwh),
            "estimated_fuel_consumption_l": float(fuel_used_l),
            "fuel_efficiency_km_per_l": (
                float(fuel_efficiency_km_l) if not np.isnan(fuel_efficiency_km_l) else None
            ),
            "eco_driving_score": float(eco_score),
        }

    def _eco_driving_score(self, trip_df: pd.DataFrame) -> float:
        """
        A 0-100 sub-score rewarding smooth, low-idle, moderate-speed
        driving -- independent of the overall safety-weighted driver
        score computed later in `scoring/`.
        """
        accel = trip_df["acceleration_mps2"]
        smoothness = 100 - min(100, float(accel.std(skipna=True) or 0) * 20)

        idle_ratio = (
            trip_df.loc[trip_df["speed_kmh"] <= THRESHOLDS.idle_speed_kmh, "dt_s"].sum()
            / max(trip_df["dt_s"].sum(), 1)
        )
        idle_penalty = idle_ratio * 100

        speed = trip_df["speed_kmh"]
        moderate_speed_ratio = (
            speed.between(40, 90).sum() / max(len(speed), 1)
        ) * 100

        score = 0.5 * smoothness + 0.3 * moderate_speed_ratio + 0.2 * (100 - idle_penalty)
        return float(np.clip(score, 0, 100))

    # ------------------------------------------------------------------
    # Driving statistics (context split)
    # ------------------------------------------------------------------
    def _driving_statistics(self, trip_df: pd.DataFrame) -> dict:
        total_time = trip_df["dt_s"].sum()
        if total_time <= 0:
            return {
                "highway_driving_pct": 0.0, "city_driving_pct": 0.0,
                "night_driving_pct": 0.0, "peak_hour_driving_pct": 0.0,
            }

        highway_mask = trip_df["speed_kmh"] >= THRESHOLDS.highway_speed_floor_kmh
        city_mask = trip_df["speed_kmh"] <= THRESHOLDS.city_speed_ceiling_kmh

        night_hours = _night_hour_mask(trip_df["hour_of_day"])
        peak_mask = trip_df["hour_of_day"].isin(THRESHOLDS.peak_hours)

        return {
            "highway_driving_pct": float(trip_df.loc[highway_mask, "dt_s"].sum() / total_time * 100),
            "city_driving_pct": float(trip_df.loc[city_mask, "dt_s"].sum() / total_time * 100),
            "night_driving_pct": float(trip_df.loc[night_hours, "dt_s"].sum() / total_time * 100),
            "peak_hour_driving_pct": float(trip_df.loc[peak_mask, "dt_s"].sum() / total_time * 100),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract_trip_features(self, trip_df: pd.DataFrame) -> dict:
        """Extract the full feature set for a single trip's DataFrame."""
        if len(trip_df) < THRESHOLDS.min_trip_points:
            raise InsufficientDataError(
                f"Trip has only {len(trip_df)} points; minimum is {THRESHOLDS.min_trip_points}."
            )

        try:
            trip_df = self._compute_point_kinematics(trip_df)
            driving = self._driving_features(trip_df)
            fuel = self._fuel_features(trip_df, driving["distance_travelled_km"])
            stats = self._driving_statistics(trip_df)
        except InsufficientDataError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FeatureEngineeringError(f"Feature extraction failed: {exc}") from exc

        features = {
            "veh_id": trip_df["veh_id"].iloc[0],
            "trip_id": trip_df["trip_id"].iloc[0],
            "global_trip_id": trip_df["global_trip_id"].iloc[0],
            "trip_start_time": trip_df["timestamp"].iloc[0],
            "trip_end_time": trip_df["timestamp"].iloc[-1],
            **driving,
            **fuel,
            **stats,
        }
        return features

    def extract_all_trips(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract features for every trip in a cleaned VED DataFrame.
        Trips that fail extraction (e.g. too few points after grouping)
        are skipped with a warning rather than crashing the whole batch.
        """
        records = []
        skipped = 0
        for trip_id, trip_df in df.groupby("global_trip_id"):
            try:
                records.append(self.extract_trip_features(trip_df))
            except InsufficientDataError:
                skipped += 1
                continue
            except FeatureEngineeringError as exc:
                self._logger.warning("Skipping trip %s: %s", trip_id, exc)
                skipped += 1
                continue

        if skipped:
            self._logger.info("Skipped %d trips during feature extraction", skipped)

        if not records:
            raise InsufficientDataError("No trips produced valid features.")

        result = pd.DataFrame.from_records(records)
        self._logger.info("Extracted features for %d trips", len(result))
        return result

    def get_point_level_kinematics(self, trip_df: pd.DataFrame) -> pd.DataFrame:
        """Public accessor used by the detection module and visualizations."""
        return self._compute_point_kinematics(trip_df.copy())


def _haversine_m(lat1, lon1, lat2, lon2) -> pd.Series:
    """Vectorized haversine distance in meters."""
    r = 6371008.8
    lat1r, lon1r, lat2r, lon2r = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    c = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return r * c


def _bearing_deg(lat1, lon1, lat2, lon2) -> pd.Series:
    """Vectorized initial bearing (heading) in degrees between consecutive GPS points."""
    lat1r, lon1r, lat2r, lon2r = map(np.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2r - lon1r
    x = np.sin(dlon) * np.cos(lat2r)
    y = np.cos(lat1r) * np.sin(lat2r) - np.sin(lat1r) * np.cos(lat2r) * np.cos(dlon)
    bearing = np.degrees(np.arctan2(x, y))
    return (bearing + 360) % 360


def _night_hour_mask(hour_series: pd.Series) -> pd.Series:
    """True where hour_of_day falls in the configured night window (wraps midnight)."""
    start, end = THRESHOLDS.night_start_hour, THRESHOLDS.night_end_hour
    if start > end:
        return (hour_series >= start) | (hour_series < end)
    return (hour_series >= start) & (hour_series < end)
