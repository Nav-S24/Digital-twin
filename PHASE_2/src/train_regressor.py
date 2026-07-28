from pathlib import Path
from typing import Optional
import joblib, numpy as np, pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor
from src.config import *
from src.train_classifier import _EXCLUDE
from src.utils import get_logger

logger = get_logger(__name__)
_RUL_EXCLUDE = _EXCLUDE | {"RUL","RUL_synthetic"}

def prepare_rul_target(df):
    df = df.copy()
    if "RUL" in df.columns:
        df["RUL_synthetic"] = False
        return df
    logger.warning("⚠ No RUL column — generating SYNTHETIC RUL from vehicle_health.")
    rng = np.random.default_rng(RANDOM_SEED)
    df["RUL"]           = (df["vehicle_health"]*2.0 + rng.normal(0,5,len(df))).clip(0,200)
    df["RUL_synthetic"] = True
    return df

def train_rul_regressor(df):
    feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c not in _RUL_EXCLUDE]
    X = df[feature_cols].values
    y = df["RUL"].values.astype(float)
    X_train,X_test,y_train,y_test = train_test_split(X,y,test_size=TEST_SIZE,random_state=RANDOM_SEED)
    model = XGBRegressor(**XGBOOST_REGRESSOR_PARAMS)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mae  = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2   = r2_score(y_test, y_pred)
    logger.info("RUL — MAE: %.4f  RMSE: %.4f  R²: %.4f", mae, rmse, r2)
    return model, {"mae":mae,"rmse":rmse,"r2":r2,
                   "synthetic_rul":bool(df.get("RUL_synthetic",pd.Series([False])).any())}

def save_regressor(model, path=None):
    p = Path(path) if path else REGRESSOR_MODEL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, p)

def load_regressor(path=None):
    p = Path(path) if path else REGRESSOR_MODEL_PATH
    return joblib.load(p)