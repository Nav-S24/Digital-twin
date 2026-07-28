from __future__ import annotations
import io, zipfile
from pathlib import Path
from typing import Optional, Union
import numpy as np
import pandas as pd
from src.utils import get_logger

logger = get_logger(__name__)

SCHEMA_COLS = ["timestamp","temperature","pressure","rpm","vibration",
               "battery_voltage","battery_current","battery_temp","fault_count","failure"]

def _ensure_schema(df, source_name):
    for col in SCHEMA_COLS:
        if col not in df.columns:
            df[col] = 0 if col == "failure" else np.nan
    df["failure"]     = df["failure"].fillna(0).astype(int)
    df["fault_count"] = df["fault_count"].fillna(0).astype(float)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df[SCHEMA_COLS + [c for c in df.columns if c not in SCHEMA_COLS]]

def _normalise_0_1(series):
    lo, hi = series.min(), series.max()
    if hi == lo: return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo)

def load_ai4i(path):
    path = Path(path)
    logger.info("[AI4I] Loading from: %s", path)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            csv_name = [n for n in zf.namelist() if n.endswith(".csv")][0]
            with zf.open(csv_name) as f:
                df = pd.read_csv(f)
    else:
        df = pd.read_csv(path)
    logger.info("[AI4I] Raw shape: %s", df.shape)

    rename = {"Air temperature [K]": "_air_k", "Process temperature [K]": "_proc_k",
              "Rotational speed [rpm]": "rpm", "Torque [Nm]": "_torque",
              "Tool wear [min]": "fault_count", "Machine failure": "failure"}
    df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})

    df["temperature"] = df["_air_k"] - 273.15 if "_air_k" in df.columns else np.nan
    if "_proc_k" in df.columns and "_air_k" in df.columns:
        delta_norm = _normalise_0_1(df["_proc_k"] - df["_air_k"])
        df["pressure"] = 45.0 - 30.0 * delta_norm
    else:
        df["pressure"] = np.nan
    df["vibration"] = _normalise_0_1(df["_torque"]) if "_torque" in df.columns else np.nan
    if "fault_count" in df.columns:
        df["fault_count"] = (15.0 * _normalise_0_1(df["fault_count"].fillna(0))).round(0)
    df["timestamp"] = pd.NaT
    df = df.drop(columns=["_air_k","_proc_k","_torque"], errors="ignore")
    df = _ensure_schema(df, "AI4I")
    df["_source"] = "ai4i"
    logger.info("[AI4I] Adapted shape: %s | failure rate: %.2f%%", df.shape, 100*df["failure"].mean())
    return df

def load_scania(path, split="train"):
    path = Path(path)
    logger.info("[Scania] Loading split='%s' from: %s", split, path)
    if path.is_file() and path.suffix == ".zip":
        fname = f"aps_failure_{split}ing_set.csv"
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if fname in n]
            if not names:
                raise FileNotFoundError(f"'{fname}' not found in zip")
            with zf.open(names[0]) as f:
                raw = f.read()
        df = pd.read_csv(io.BytesIO(raw), skiprows=20, na_values=["na","NA","Na",""])
    else:
        df = pd.read_csv(path, skiprows=20, na_values=["na","NA","Na",""])
    logger.info("[Scania] Raw shape: %s", df.shape)

    if "class" in df.columns:
        failure_vals = (df["class"].str.strip().str.lower() == "pos").astype(int).values
        df = df.drop(columns=["class"]).copy()
        df["failure"] = failure_vals
    else:
        df["failure"] = 0

    schema_map = {"aa_000":"temperature","ab_000":"pressure",
                  "ac_000":"rpm","ad_000":"vibration","ba_000":"fault_count"}
    df = df.rename(columns={k:v for k,v in schema_map.items() if k in df.columns})

    for col, lo, hi in [("temperature",40,120),("pressure",15,45),("rpm",500,6500)]:
        if col in df.columns:
            df[col] = lo + (hi-lo)*_normalise_0_1(df[col].fillna(df[col].median()))
    if "vibration" in df.columns:
        df["vibration"] = _normalise_0_1(df["vibration"].fillna(df["vibration"].median()))
    if "fault_count" in df.columns:
        df["fault_count"] = (15.0*_normalise_0_1(df["fault_count"].fillna(0))).round(0)

    # Keep a few extra sensor groups as ML features
    extra_rename = {}
    for grp in ["ae","af","ag","bk","bl","bm","ee"]:
        for col in [c for c in df.columns if c.startswith(f"{grp}_")][:3]:
            extra_rename[col] = f"scania_{col}"
    df = df.rename(columns=extra_rename)
    keep = set(SCHEMA_COLS) | set(extra_rename.values()) | {"failure"}
    df = df.drop(columns=[c for c in df.columns if c not in keep], errors="ignore").copy()

    df["timestamp"] = pd.NaT
    df = _ensure_schema(df, "Scania")
    df["_source"] = "scania"
    logger.info("[Scania] Adapted shape: %s | failure rate: %.2f%%", df.shape, 100*df["failure"].mean())
    return df

def merge_datasets(dfs, reset_index=True):
    non_empty = [d for d in dfs if not d.empty]
    if not non_empty:
        raise ValueError("All DataFrames are empty.")
    merged = pd.concat(non_empty, ignore_index=True, sort=False)
    merged = merged.sample(frac=1.0, random_state=42)
    if reset_index:
        merged = merged.reset_index(drop=True)
    logger.info("[Merge] shape: %s | failure rate: %.2f%%", merged.shape, 100*merged["failure"].mean())
    return merged