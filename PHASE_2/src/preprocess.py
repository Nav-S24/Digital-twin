from pathlib import Path
from typing import Optional
import joblib, numpy as np, pandas as pd
from scipy import stats
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from src.config import *
from src.utils import detect_numeric_columns, get_logger, log_dataset_stats, remap_columns

logger = get_logger(__name__)

def load_and_clean(path=None, df_raw=None, column_mapping=None):
    if df_raw is not None:
        df = df_raw.copy()
    elif path is not None:
        df = pd.read_csv(Path(path))
    else:
        raise ValueError("Provide path or df_raw.")
    if column_mapping:
        df = remap_columns(df, column_mapping)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in SENSOR_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    if "failure" not in df.columns:
        df["failure"] = 0
    num_cols = detect_numeric_columns(df)
    df[num_cols] = df[num_cols].fillna(df[num_cols].median())
    df = df.drop_duplicates().reset_index(drop=True)
    sensor_num = [c for c in SENSOR_COLUMNS if c in num_cols]
    for col in sensor_num:
        q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
        iqr = q3 - q1
        df[col] = df[col].clip(q1 - 1.5*iqr, q3 + 1.5*iqr)
    logger.info("Cleaned shape: %s", df.shape)
    return df

def scale_features(df, fit=True, scaler=None, columns=None):
    df = df.copy()
    if columns is None:
        columns = [c for c in SENSOR_COLUMNS if c in df.columns]
    if fit:
        scaler = MinMaxScaler() if SCALER_TYPE == "minmax" else StandardScaler()
        df[columns] = scaler.fit_transform(df[columns])
    else:
        df[columns] = scaler.transform(df[columns])
    return df, scaler

def save_scaler(scaler, path=None):
    p = Path(path) if path else SCALER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, p)

def load_scaler(path=None):
    p = Path(path) if path else SCALER_PATH
    return joblib.load(p)