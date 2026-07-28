import logging, sys
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

def get_logger(name, log_file=None, level=logging.INFO):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                            datefmt="%H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger

def log_dataset_stats(df, logger, label="dataset"):
    logger.info(f"[{label}] shape: {df.shape}")
    missing = df.isnull().sum()
    missing = missing[missing > 0]
    if not missing.empty:
        logger.warning(f"[{label}] missing:\n{missing.to_string()}")

def detect_numeric_columns(df):
    return df.select_dtypes(include=[np.number]).columns.tolist()

def clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))

def remap_columns(df, mapping):
    available = {k: v for k, v in mapping.items() if k in df.columns}
    return df.rename(columns=available)

def generate_synthetic_dataset(n_rows=2000, seed=42):
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(start="2024-01-01", periods=n_rows, freq="1min")
    temperature     = rng.normal(85, 15, n_rows).clip(40, 140)
    pressure        = rng.normal(30, 6, n_rows).clip(5, 60)
    rpm             = rng.normal(2500, 800, n_rows).clip(500, 7000)
    vibration       = rng.exponential(0.25, n_rows).clip(0, 2)
    battery_voltage = rng.normal(12.4, 0.4, n_rows).clip(10, 15)
    battery_current = rng.normal(50, 20, n_rows).clip(0, 150)
    battery_temp    = rng.normal(35, 10, n_rows).clip(10, 80)
    fault_count     = rng.integers(0, 10, n_rows)
    failure_prob = (0.3*(temperature>105).astype(float) +
                   0.3*(fault_count>6).astype(float) +
                   0.1*rng.random(n_rows))
    failure = (failure_prob > 0.4).astype(int)
    return pd.DataFrame({
        "timestamp": timestamps, "temperature": temperature,
        "pressure": pressure, "rpm": rpm, "vibration": vibration,
        "battery_voltage": battery_voltage, "battery_current": battery_current,
        "battery_temp": battery_temp, "fault_count": fault_count.astype(float),
        "failure": failure,
    })