from typing import Optional
import numpy as np, pandas as pd
from src.config import ROLLING_WINDOW
from src.utils import get_logger

logger = get_logger(__name__)
ENGINEERED_COLUMNS = ["temp_pressure_ratio","rpm_per_temperature","vibration_risk",
                      "thermal_stress","fault_density","rolling_mean_temp",
                      "rolling_mean_rpm","rolling_std_vibration"]

def engineer_features(df, window=None):
    df = df.copy()
    window = window or ROLLING_WINDOW
    with np.errstate(divide="ignore", invalid="ignore"):
        df["temp_pressure_ratio"] = np.where(df["pressure"]!=0, df["temperature"]/df["pressure"], np.nan)
        df["rpm_per_temperature"] = np.where(df["temperature"]!=0, df["rpm"]/df["temperature"], np.nan)
    vib_max = df["vibration"].max() or 1.0
    df["vibration_risk"] = (df["vibration"]/vib_max).clip(0,1)
    temp_max = df["temperature"].max() or 1.0
    batt_max = df["battery_temp"].max() or 1.0
    df["thermal_stress"] = (0.6*df["temperature"]/temp_max + 0.4*df["battery_temp"]/batt_max).clip(0,1)
    fault_ref = max(df["fault_count"].max(), 10.0)
    df["fault_density"] = (df["fault_count"]/fault_ref).clip(0,1)
    df["rolling_mean_temp"]      = df["temperature"].rolling(window, min_periods=1).mean()
    df["rolling_mean_rpm"]       = df["rpm"].rolling(window, min_periods=1).mean()
    df["rolling_std_vibration"]  = df["vibration"].rolling(window, min_periods=1).std().fillna(0)
    for col in ENGINEERED_COLUMNS:
        if df[col].isnull().any():
            df[col] = df[col].fillna(df[col].median())
    logger.info("Feature engineering complete.")
    return df