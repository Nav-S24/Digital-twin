"""
Phase 2: Predictive Maintenance & Failure Prediction
End-to-end pipeline: C-MAPSS + AI4I + Phase1 Output.csv
─────────────────────────────────────────────────────────
Run:  python phase2_pipeline.py
      (set DATA_DIR paths in CONFIG before running)
"""

# ─── stdlib ───────────────────────────────────────────────────────────────────
import os
import warnings
import json
warnings.filterwarnings("ignore")

# ─── third-party ──────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MinMaxScaler, LabelEncoder
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (
    mean_squared_error, mean_absolute_error,
    classification_report, roc_auc_score, confusion_matrix
)
from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb
import shap
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import joblib
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG  ← set your actual file paths here
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    # Folder containing train_FD001.txt … test_FD004.txt … RUL_FD001.txt …
    "cmapss_dir":  "../data/CMAPSSData",

    # Path to AI4I 2020 CSV (downloaded from UCI)
    "ai4i_path":   "../data/ai4i2020.csv",

    # Phase 1 output
    "phase1_path":  "Output.csv",

    # Where to save trained models
    "models_dir": "models",

    # Which C-MAPSS subset to use  (FD001 = single condition, easiest to start)
    "cmapss_subset": "FD001",

    # Sequence window length for LSTM
    "seq_len":  30,

    # RUL cap (cycles beyond this are treated as 'healthy baseline')
    "rul_cap":  125,

    # Failure-imminent threshold (cycles)
    "rul_alert_threshold": 30,

    # Random seed
    "seed": 42,
}

os.makedirs(CONFIG["models_dir"], exist_ok=True)
np.random.seed(CONFIG["seed"])
torch.manual_seed(CONFIG["seed"])


# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

# C-MAPSS column names (from the dataset readme)
CMAPSS_COLS = (
    ["unit", "cycle"]
    + [f"op{i}" for i in range(1, 4)]          # 3 operational settings
    + [f"s{i}" for i in range(1, 22)]           # 21 sensor readings
)

# AI4I column names (matches your screenshot)
AI4I_COLS = [
    "UDI", "Product_ID", "Type",
    "Air_temp_K", "Process_temp_K",
    "Rotational_speed_rpm", "Torque_Nm", "Tool_wear_min",
    "Machine_failure",
    "TWF", "HDF", "PWF", "OSF", "RNF"
]


def load_cmapss(subset: str):
    """Load one C-MAPSS subset and compute RUL labels."""
    d = CONFIG["cmapss_dir"]

    def _read(fname):
        return pd.read_csv(
            os.path.join(d, fname),
            sep=r"\s+", header=None, names=CMAPSS_COLS
        )

    train = _read(f"train_{subset}.txt")
    test  = _read(f"test_{subset}.txt")
    rul   = pd.read_csv(
        os.path.join(d, f"RUL_{subset}.txt"),
        header=None, names=["rul_at_end"]
    )

    # ── Train: RUL = max_cycle_for_unit − current_cycle, capped ──────────────
    max_cycles      = train.groupby("unit")["cycle"].max().rename("max_cycle")
    train           = train.join(max_cycles, on="unit")
    train["rul"]    = (train["max_cycle"] - train["cycle"]).clip(upper=CONFIG["rul_cap"])
    train["label"]  = (train["rul"] <= CONFIG["rul_alert_threshold"]).astype(int)
    train.drop(columns=["max_cycle"], inplace=True)

    # ── Test: each unit's last row → true RUL from RUL file ──────────────────
    last_test       = test.groupby("unit").tail(1).copy().reset_index(drop=True)
    last_test["rul"] = rul["rul_at_end"].clip(upper=CONFIG["rul_cap"]).values
    last_test["label"] = (last_test["rul"] <= CONFIG["rul_alert_threshold"]).astype(int)

    print(f"[C-MAPSS {subset}] train={len(train):,} rows | "
          f"test units={last_test['unit'].nunique()} | "
          f"failure-imminent in train: {train['label'].mean():.1%}")
    return train, last_test


def load_ai4i():
    """Load AI4I 2020 dataset."""
    try:
        df = pd.read_csv(CONFIG["ai4i_path"])
        # Handle column name variations across different download sources
        rename = {}
        col_map = {
            "Air temperature [K]":          "Air_temp_K",
            "Process temperature [K]":      "Process_temp_K",
            "Rotational speed [rpm]":       "Rotational_speed_rpm",
            "Torque [Nm]":                  "Torque_Nm",
            "Tool wear [min]":              "Tool_wear_min",
            "Machine failure":              "Machine_failure",
            "Product ID":                   "Product_ID",
        }
        for old, new in col_map.items():
            if old in df.columns:
                rename[old] = new
        df.rename(columns=rename, inplace=True)
    except FileNotFoundError:
        print("[AI4I] File not found — generating synthetic stand-in data")
        df = _synthetic_ai4i(10000)

    failure_modes = ["TWF", "HDF", "PWF", "OSF", "RNF"]
    for m in failure_modes:
        if m not in df.columns:
            df[m] = 0

    print(f"[AI4I] rows={len(df):,} | failure rate={df['Machine_failure'].mean():.1%}")
    return df


def _synthetic_ai4i(n):
    """Fallback: synthetic AI4I-like data if the real file is missing."""
    np.random.seed(42)
    df = pd.DataFrame({
        "UDI":               range(1, n + 1),
        "Product_ID":        [f"L{i}" for i in range(n)],
        "Type":              np.random.choice(["L", "M", "H"], n),
        "Air_temp_K":        np.random.normal(300, 2, n),
        "Process_temp_K":    np.random.normal(310, 2, n),
        "Rotational_speed_rpm": np.random.normal(1500, 200, n),
        "Torque_Nm":         np.random.normal(40, 10, n),
        "Tool_wear_min":     np.random.uniform(0, 250, n),
        "Machine_failure":   np.random.choice([0, 1], n, p=[0.966, 0.034]),
        "TWF": 0, "HDF": 0, "PWF": 0, "OSF": 0, "RNF": 0
    })
    return df


def load_phase1():
    """Load Phase 1 Output.csv."""
    df = pd.read_csv(CONFIG["phase1_path"])
    print(f"[Phase1] rows={len(df):,} | failure rate={df['failure'].mean():.1%}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 2. FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════════════════════

# C-MAPSS sensors to keep (drop near-constant ones — verified via variance analysis)
CMAPSS_DROP_SENSORS = ["s1", "s5", "s6", "s10", "s16", "s18", "s19"]

CMAPSS_KEEP_SENSORS = [s for s in [f"s{i}" for i in range(1, 22)]
                       if s not in CMAPSS_DROP_SENSORS]


def drop_low_variance(df, cols, threshold=0.01):
    """Drop sensor columns whose std < threshold after normalisation."""
    low_var = [c for c in cols if df[c].std() < threshold]
    if low_var:
        print(f"  → dropping low-variance sensors: {low_var}")
    return [c for c in cols if c not in low_var]


def engineer_cmapss_features(df: pd.DataFrame, sensors: list, window: int = 30):
    """
    For each sensor add:
      • rolling mean  (window)
      • rolling std   (window)
      • lag-1 value
      • delta (current − lag1)
    """
    df = df.copy().sort_values(["unit", "cycle"])

    for s in sensors:
        grp = df.groupby("unit")[s]
        df[f"{s}_rmean"] = grp.transform(
            lambda x: x.rolling(window, min_periods=1).mean())
        df[f"{s}_rstd"] = grp.transform(
            lambda x: x.rolling(window, min_periods=1).std().fillna(0))
        df[f"{s}_lag1"] = grp.shift(1).bfill()
        df[f"{s}_delta"] = df[s] - df[f"{s}_lag1"]

    # Normalise within operating condition (FD001 = single condition)
    op_cols = ["op1", "op2", "op3"]
    scaler  = MinMaxScaler()
    feat_cols = sensors + [f"{s}_rmean" for s in sensors] + \
                [f"{s}_rstd" for s in sensors] + \
                [f"{s}_lag1" for s in sensors] + \
                [f"{s}_delta" for s in sensors]
    df[feat_cols] = scaler.fit_transform(df[feat_cols])
    return df, scaler, feat_cols


def engineer_ai4i_features(df: pd.DataFrame):
    """Feature engineering for AI4I dataset."""
    df = df.copy()

    # Type encoding
    type_map = {"L": 0, "M": 1, "H": 2}
    df["Type_enc"] = df["Type"].map(type_map).fillna(0).astype(int)

    # Derived features
    df["temp_diff"]         = df["Process_temp_K"] - df["Air_temp_K"]
    df["power_kW"]          = df["Torque_Nm"] * df["Rotational_speed_rpm"] / 9549
    df["wear_rate"]         = df["Tool_wear_min"] / (df["Rotational_speed_rpm"] + 1)
    df["torque_x_wear"]     = df["Torque_Nm"] * df["Tool_wear_min"]
    df["speed_x_torque"]    = df["Rotational_speed_rpm"] * df["Torque_Nm"]

    feat_cols = [
        "Air_temp_K", "Process_temp_K", "Rotational_speed_rpm",
        "Torque_Nm", "Tool_wear_min", "Type_enc",
        "temp_diff", "power_kW", "wear_rate", "torque_x_wear", "speed_x_torque"
    ]
    return df, feat_cols


def engineer_phase1_features(df: pd.DataFrame):
    """Use Phase 1 health scores as rich derived features."""
    df = df.copy()

    # Composite risk scores
    df["health_risk"]        = 100 - df["vehicle_health"]
    df["engine_risk"]        = 100 - df["engine_health"]
    df["battery_risk"]       = 100 - df["battery_health"]
    df["composite_risk"]     = (
        0.4 * df["engine_risk"] +
        0.3 * df["battery_risk"] +
        0.2 * (100 - df["ml_health_score"]) +
        0.1 * df["fault_count"]
    )
    df["readiness_gap"]      = 100 - df["trip_readiness"]

    feat_cols = [
        # Raw sensors
        "temperature", "pressure", "rpm", "vibration",
        "battery_voltage", "battery_current", "battery_temp", "fault_count",
        # Phase 1 health scores
        "engine_health", "battery_health", "vehicle_health",
        "ml_health_score", "trip_readiness",
        # Derived
        "health_risk", "engine_risk", "battery_risk",
        "composite_risk", "readiness_gap",
        # Ordinal class
        "health_class_id",
    ]
    return df, feat_cols


# ══════════════════════════════════════════════════════════════════════════════
# 3. LSTM MODEL
# ══════════════════════════════════════════════════════════════════════════════

class RUL_LSTM(nn.Module):
    def __init__(self, input_size, hidden=64, layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size, hidden, layers,
            batch_first=True, dropout=dropout
        )
        self.fc = nn.Linear(hidden, 1)
        self.relu = nn.ReLU()           # RUL is non-negative

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.relu(self.fc(out[:, -1, :])).squeeze()


def build_sequences(df: pd.DataFrame, feat_cols: list, seq_len: int):
    """
    Build (N, seq_len, features) tensor from per-unit time-ordered rows.
    Label for each window = RUL at the last cycle in the window.
    """
    X_list, y_list = [], []
    for unit, grp in df.groupby("unit"):
        grp  = grp.sort_values("cycle")
        vals = grp[feat_cols].values
        ruls = grp["rul"].values
        for i in range(len(vals) - seq_len + 1):
            X_list.append(vals[i : i + seq_len])
            y_list.append(ruls[i + seq_len - 1])
    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32)


def train_lstm(X_train, y_train, X_val, y_val, input_size,
               epochs=80, batch=256, lr=1e-3, patience=10):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model  = RUL_LSTM(input_size).to(device)
    opt    = torch.optim.Adam(model.parameters(), lr=lr)
    sched  = torch.optim.lr_scheduler.ReduceLROnPlateau(
                 opt, factor=0.5, patience=5)
    crit   = nn.L1Loss()

    train_ds = TensorDataset(torch.tensor(X_train), torch.tensor(y_train))
    val_ds   = TensorDataset(torch.tensor(X_val),   torch.tensor(y_val))
    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl   = DataLoader(val_ds,   batch_size=batch)

    best_val, wait, best_state = np.inf, 0, None

    for ep in range(epochs):
        model.train()
        for xb, yb in train_dl:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb)
            loss = crit(pred, yb)
            opt.zero_grad(); loss.backward(); opt.step()

        model.eval()
        val_losses = []
        with torch.no_grad():
            for xb, yb in val_dl:
                xb, yb = xb.to(device), yb.to(device)
                val_losses.append(crit(model(xb), yb).item())
        val_loss = np.mean(val_losses)
        sched.step(val_loss)

        if val_loss < best_val:
            best_val, wait = val_loss, 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                print(f"  Early stop at epoch {ep+1} | best val MAE={best_val:.2f}")
                break

        if (ep + 1) % 10 == 0:
            print(f"  Epoch {ep+1:3d} | val MAE={val_loss:.2f}")

    model.load_state_dict(best_state)
    return model


def lstm_predict(model, X, batch=256):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model  = model.to(device).eval()
    preds  = []
    ds     = DataLoader(TensorDataset(torch.tensor(X)), batch_size=batch)
    with torch.no_grad():
        for (xb,) in ds:
            preds.extend(model(xb.to(device)).cpu().numpy().tolist())
    return np.array(preds)


# ══════════════════════════════════════════════════════════════════════════════
# 4. MAIN TRAINING PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline():
    subset  = CONFIG["cmapss_subset"]
    seq_len = CONFIG["seq_len"]

    print("\n" + "="*60)
    print("  PHASE 2 — PREDICTIVE MAINTENANCE PIPELINE")
    print("="*60)

    # ── 4.1  Load data ────────────────────────────────────────────────────────
    print("\n[1/6] Loading datasets...")
    train_cmapss, test_cmapss = load_cmapss(subset)
    ai4i_df  = load_ai4i()
    phase1   = load_phase1()

    # ── 4.2  Feature engineering ──────────────────────────────────────────────
    print("\n[2/6] Engineering features...")

    # C-MAPSS
    sensors = drop_low_variance(train_cmapss, CMAPSS_KEEP_SENSORS)
    train_cmapss, cmapss_scaler, cmapss_feats = engineer_cmapss_features(
        train_cmapss, sensors, window=seq_len
    )
    test_cmapss, _, _ = engineer_cmapss_features(
        test_cmapss, sensors, window=seq_len
    )
    # apply same scaler to test
    #test_cmapss[cmapss_feats] = cmapss_scaler.transform(test_cmapss[cmapss_feats])
    joblib.dump(cmapss_scaler,
            f"{CONFIG['models_dir']}/cmapss_scaler.pkl")

    joblib.dump(cmapss_feats,
            f"{CONFIG['models_dir']}/cmapss_feats.pkl")

    print(f"  C-MAPSS feature count: {len(cmapss_feats)}")

    # AI4I
    ai4i_df, ai4i_feats = engineer_ai4i_features(ai4i_df)
    ai4i_scaler = MinMaxScaler()
    ai4i_df[ai4i_feats] = ai4i_scaler.fit_transform(ai4i_df[ai4i_feats])
    joblib.dump(ai4i_scaler, f"{CONFIG['models_dir']}/ai4i_scaler.pkl")
    print(f"  AI4I feature count: {len(ai4i_feats)}")

    # Phase 1
    phase1, p1_feats = engineer_phase1_features(phase1)
    p1_scaler = MinMaxScaler()
    phase1[p1_feats] = p1_scaler.fit_transform(phase1[p1_feats])
    joblib.dump(p1_scaler, f"{CONFIG['models_dir']}/phase1_scaler.pkl")
    print(f"  Phase1 feature count: {len(p1_feats)}")

    # ── 4.3  LSTM — RUL Regression on C-MAPSS ────────────────────────────────
    print("\n[3/6] Training LSTM for RUL regression (C-MAPSS)...")
    units     = train_cmapss["unit"].unique()
    val_units = np.random.choice(units, size=max(1, int(0.15 * len(units))), replace=False)
    tr_mask   = ~train_cmapss["unit"].isin(val_units)

    X_seq_tr, y_seq_tr = build_sequences(train_cmapss[tr_mask],  cmapss_feats, seq_len)
    X_seq_val, y_seq_val = build_sequences(train_cmapss[~tr_mask], cmapss_feats, seq_len)

    print(f"  LSTM train sequences: {len(X_seq_tr):,} | val: {len(X_seq_val):,}")
    lstm_model = train_lstm(X_seq_tr, y_seq_tr, X_seq_val, y_seq_val,
                            input_size=len(cmapss_feats))
    torch.save(lstm_model.state_dict(),
               f"{CONFIG['models_dir']}/lstm_rul.pt")
    print("  LSTM saved.")

    # ── 4.4  XGBoost — RUL Regression + Failure Classification ──────────────
    print("\n[4/6] Training XGBoost (C-MAPSS + Phase1)...")

    # --- 4.4a XGBoost RUL regressor (C-MAPSS) --------------------------------
    X_tr  = train_cmapss[tr_mask][cmapss_feats]
    y_rul = train_cmapss[tr_mask]["rul"]
    X_val2 = train_cmapss[~tr_mask][cmapss_feats]
    y_val2 = train_cmapss[~tr_mask]["rul"]

    xgb_rul = xgb.XGBRegressor(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=CONFIG["seed"], tree_method="hist",
        early_stopping_rounds=20, eval_metric="rmse"
    )
    xgb_rul.fit(X_tr, y_rul, eval_set=[(X_val2, y_val2)])
    joblib.dump(xgb_rul, f"{CONFIG['models_dir']}/xgb_rul.pkl")

    # Evaluate on test set
    rul_xgb_pred = xgb_rul.predict(test_cmapss[cmapss_feats])
    rmse = np.sqrt(mean_squared_error(test_cmapss["rul"], rul_xgb_pred))
    mae  = mean_absolute_error(test_cmapss["rul"], rul_xgb_pred)
    print(f"  XGBoost RUL → RMSE={rmse:.2f} | MAE={mae:.2f} cycles")

    # --- 4.4b XGBoost Failure Classifier (Phase1 data) -----------------------
    X_p1 = phase1[p1_feats]
    y_p1 = phase1["failure"]
    X_p1_tr, X_p1_val, y_p1_tr, y_p1_val = train_test_split(
        X_p1, y_p1, test_size=0.2, stratify=y_p1, random_state=CONFIG["seed"]
    )
    pos_ratio = (y_p1_tr == 0).sum() / max(1, (y_p1_tr == 1).sum())
    xgb_cls = xgb.XGBClassifier(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=pos_ratio,
        use_label_encoder=False, eval_metric="logloss",
        random_state=CONFIG["seed"], tree_method="hist",
        early_stopping_rounds=15
    )
    xgb_cls.fit(X_p1_tr, y_p1_tr,
                eval_set=[(X_p1_val, y_p1_val)])
    joblib.dump(xgb_cls, f"{CONFIG['models_dir']}/xgb_cls.pkl")
    joblib.dump(p1_feats, f"{CONFIG['models_dir']}/p1_feats.pkl")

    y_prob = xgb_cls.predict_proba(X_p1_val)[:, 1]
    auc    = roc_auc_score(y_p1_val, y_prob)
    print(f"  XGBoost Failure Cls → AUC={auc:.4f}")
    print(classification_report(y_p1_val, (y_prob >= 0.5).astype(int),
                                target_names=["No failure", "Failure"]))

    # ── 4.5  Random Forest — Failure Mode (AI4I) ─────────────────────────────
    print("[5/6] Training Random Forest — failure mode classifier (AI4I)...")
    failure_modes = ["TWF", "HDF", "PWF", "OSF", "RNF"]
    available_modes = [m for m in failure_modes if m in ai4i_df.columns
                       and ai4i_df[m].sum() > 5]

    # Build multi-label → single mode label (dominant mode per row)
    if available_modes:
        ai4i_df["failure_mode"] = ai4i_df[available_modes].idxmax(axis=1)
        ai4i_df.loc[ai4i_df["Machine_failure"] == 0, "failure_mode"] = "NONE"
    else:
        ai4i_df["failure_mode"] = ai4i_df["Machine_failure"].map({0: "NONE", 1: "GENERIC"})

    le   = LabelEncoder()
    y_fm = le.fit_transform(ai4i_df["failure_mode"])
    X_fm = ai4i_df[ai4i_feats]
    joblib.dump(le, f"{CONFIG['models_dir']}/failure_mode_encoder.pkl")
    joblib.dump(ai4i_feats, f"{CONFIG['models_dir']}/ai4i_feats.pkl")

    X_fm_tr, X_fm_val, y_fm_tr, y_fm_val = train_test_split(
        X_fm, y_fm, test_size=0.2, stratify=y_fm, random_state=CONFIG["seed"]
    )
    rf = RandomForestClassifier(
        n_estimators=200, class_weight="balanced",
        random_state=CONFIG["seed"], n_jobs=-1
    )
    rf.fit(X_fm_tr, y_fm_tr)
    # Probability calibration for better uncertainty estimates
    rf_cal = CalibratedClassifierCV(rf, cv=3, method="sigmoid")
    rf_cal.fit(X_fm_tr, y_fm_tr)
    joblib.dump(rf_cal, f"{CONFIG['models_dir']}/rf_failure_mode.pkl")

    acc = rf_cal.score(X_fm_val, y_fm_val)
    print(f"  RF Failure Mode → Accuracy={acc:.4f}")
    print(classification_report(y_fm_val, rf_cal.predict(X_fm_val),
                                target_names=le.classes_))

    # ── 4.6  SHAP explainer ───────────────────────────────────────────────────
    print("[6/6] Building SHAP explainer...")
    explainer = shap.TreeExplainer(xgb_cls)
    joblib.dump(explainer, f"{CONFIG['models_dir']}/shap_explainer.pkl")

    # Quick SHAP summary on validation set
    shap_vals = explainer.shap_values(X_p1_val)
    feature_importance = pd.DataFrame({
        "feature": p1_feats,
        "mean_shap": np.abs(shap_vals).mean(axis=0)
    }).sort_values("mean_shap", ascending=False)

    print("\n  Top-10 features by SHAP importance:")
    print(feature_importance.head(10).to_string(index=False))
    feature_importance.to_csv(f"{CONFIG['models_dir']}/shap_importance.csv", index=False)

    # ── Save LSTM eval ────────────────────────────────────────────────────────
    print("\n[LSTM eval on test set...]")
    # Build last-window sequence for each test unit
    X_seq_test = []
    for unit, grp in test_cmapss.groupby("unit"):
        grp  = grp.sort_values("cycle")
        vals = grp[cmapss_feats].values
        if len(vals) >= seq_len:
            X_seq_test.append(vals[-seq_len:])
        else:
            pad = np.zeros((seq_len - len(vals), len(cmapss_feats)))
            X_seq_test.append(np.vstack([pad, vals]))
    X_seq_test = np.array(X_seq_test, dtype=np.float32)
    lstm_preds = lstm_predict(lstm_model, X_seq_test)
    X_seq_test = np.nan_to_num(
    X_seq_test,
    nan=0.0,
    posinf=0.0,
    neginf=0.0
)
    #lstm_rmse  = np.sqrt(mean_squared_error(test_cmapss["rul"], lstm_preds))
    #lstm_mae   = mean_absolute_error(test_cmapss["rul"], lstm_preds)
   # print(f"  LSTM RUL → RMSE={lstm_rmse:.2f} | MAE={lstm_mae:.2f} cycles")
    print("\n[LSTM eval skipped - test set contains only final engine states]")

    # ── Ensemble RUL ──────────────────────────────────────────────────────────
    #ens_rul  = 0.6 * lstm_preds + 0.4 * rul_xgb_pred
    #ens_rmse = np.sqrt(mean_squared_error(test_cmapss["rul"], ens_rul))
    #ens_mae  = mean_absolute_error(test_cmapss["rul"], ens_rul)
    #print(f"  Ensemble RUL → RMSE={ens_rmse:.2f} | MAE={ens_mae:.2f} cycles")
    print("Ensemble evaluation skipped.")
    print("\n✅ All models saved to:", CONFIG["models_dir"])
    print("  xgb_rul.pkl | xgb_cls.pkl | lstm_rul.pt")
    print("  rf_failure_mode.pkl | shap_explainer.pkl")
    print("  *_scaler.pkl | *_feats.pkl\n")

    return {
        "xgb_rul": xgb_rul, "xgb_cls": xgb_cls,
        "lstm_model": lstm_model, "rf_cal": rf_cal,
        "explainer": explainer,
        "cmapss_feats": cmapss_feats, "p1_feats": p1_feats,
        "ai4i_feats": ai4i_feats,
        "cmapss_scaler": cmapss_scaler,
        "p1_scaler": p1_scaler, "ai4i_scaler": ai4i_scaler,
        "le": le, "seq_len": seq_len,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. RECOMMENDATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

SENSOR_TO_SYSTEM = {
    "temperature":    ("Cooling system",        "Inspect coolant level and radiator"),
    "vibration":      ("Engine mounts / bearings", "Check for mechanical loosening"),
    "oil_pressure":   ("Lubrication circuit",   "Check oil level and pump"),
    "engine_health":  ("Engine subsystem",      "Run full engine diagnostics"),
    "battery_health": ("Battery / BMS",         "Inspect battery cells and connections"),
    "rpm":            ("Drivetrain",            "Check transmission and drive shaft"),
    "fault_count":    ("ECU fault logs",        "Review and clear fault codes"),
    "composite_risk": ("Overall vehicle health","Schedule comprehensive service"),
}

AVG_DAILY_CYCLES = 2.4   # Indian urban usage (derived from VED)
RUL_SAFETY_FACTOR = 0.6  # conservative booking


def get_urgency(fail_prob: float, rul_cycles: float) -> str:
    if fail_prob >= 0.80 or rul_cycles <= 10:   return "CRITICAL"
    if fail_prob >= 0.55 or rul_cycles <= 30:   return "HIGH"
    if fail_prob >= 0.30 or rul_cycles <= 60:   return "MEDIUM"
    return "LOW"


def get_top_sensors(shap_vals: np.ndarray, feat_names: list, top_n: int = 3):
    pairs = sorted(zip(feat_names, shap_vals), key=lambda x: abs(x[1]), reverse=True)
    return [{"sensor": f, "shap_value": round(float(v), 4)} for f, v in pairs[:top_n]]


def build_recommendations(top_sensors: list, rul_cycles: float, fail_prob: float):
    recs = []
    book_days = max(1, int(rul_cycles / AVG_DAILY_CYCLES * RUL_SAFETY_FACTOR))

    for rank, item in enumerate(top_sensors, 1):
        sensor = item["sensor"]
        # Fuzzy match sensor name to system
        matched = next((v for k, v in SENSOR_TO_SYSTEM.items() if k in sensor), None)
        if matched is None:
            matched = ("Vehicle system", "Inspect flagged sensor")
        system, action = matched

        trend = "rapidly deteriorating" if item["shap_value"] > 0.3 else "elevated"
        recs.append({
            "priority":        rank,
            "system":          system,
            "action":          action,
            "reason":          f"{sensor} signal is {trend} (SHAP={item['shap_value']:.3f})",
            "book_within_days": book_days,
        })
    return recs


# ══════════════════════════════════════════════════════════════════════════════
# 6. ENSEMBLE PREDICTOR (used by API)
# ══════════════════════════════════════════════════════════════════════════════

class PredictionEngine:
    """
    Wraps the trained ensemble and exposes a single .predict() method.
    Also loadable from saved files — no retraining needed for the API.
    """

    def __init__(self, models: dict):
        self.xgb_rul       = models["xgb_rul"]
        self.xgb_cls       = models["xgb_cls"]
        self.lstm_model    = models["lstm_model"]
        self.rf_cal        = models["rf_cal"]
        self.explainer     = models["explainer"]
        self.cmapss_feats  = models["cmapss_feats"]
        self.p1_feats      = models["p1_feats"]
        self.ai4i_feats    = models["ai4i_feats"]
        self.cmapss_scaler = models["cmapss_scaler"]
        self.p1_scaler     = models["p1_scaler"]
        self.ai4i_scaler   = models["ai4i_scaler"]
        self.le            = models["le"]
        self.seq_len       = models["seq_len"]

    @classmethod
    def from_disk(cls, models_dir: str = "models"):
        """Load all saved artefacts from disk."""
        lstm = RUL_LSTM(
            input_size=len(joblib.load(f"{models_dir}/cmapss_scaler.pkl").scale_)
        )
        lstm.load_state_dict(torch.load(f"{models_dir}/lstm_rul.pt",
                                        map_location="cpu"))
        lstm.eval()
        return cls({
            "xgb_rul":       joblib.load(f"{models_dir}/xgb_rul.pkl"),
            "xgb_cls":       joblib.load(f"{models_dir}/xgb_cls.pkl"),
            "lstm_model":    lstm,
            "rf_cal":        joblib.load(f"{models_dir}/rf_failure_mode.pkl"),
            "explainer":     joblib.load(f"{models_dir}/shap_explainer.pkl"),
            "cmapss_feats":  joblib.load(f"{models_dir}/p1_feats.pkl"),  # reuse p1
            "p1_feats":      joblib.load(f"{models_dir}/p1_feats.pkl"),
            "ai4i_feats":    joblib.load(f"{models_dir}/ai4i_feats.pkl"),
            "cmapss_scaler": joblib.load(f"{models_dir}/cmapss_scaler.pkl"),
            "p1_scaler":     joblib.load(f"{models_dir}/phase1_scaler.pkl"),
            "ai4i_scaler":   joblib.load(f"{models_dir}/ai4i_scaler.pkl"),
            "le":            joblib.load(f"{models_dir}/failure_mode_encoder.pkl"),
            "seq_len":       CONFIG["seq_len"],
        })

    def predict(self, vehicle_id: str, sensor_row: dict) -> dict:
        """
        sensor_row must contain the same keys as Phase 1 Output.csv columns
        (raw sensors + health scores).
        Returns a structured prediction dict.
        """
        # Build Phase-1-style feature vector
        df_row = pd.DataFrame([sensor_row])

        # Add derived features (same as engineer_phase1_features)
        df_row["health_risk"]    = 100 - df_row["vehicle_health"]
        df_row["engine_risk"]    = 100 - df_row["engine_health"]
        df_row["battery_risk"]   = 100 - df_row["battery_health"]
        df_row["composite_risk"] = (
            0.4 * df_row["engine_risk"] +
            0.3 * df_row["battery_risk"] +
            0.2 * (100 - df_row["ml_health_score"]) +
            0.1 * df_row["fault_count"]
        )
        df_row["readiness_gap"] = 100 - df_row["trip_readiness"]

        # Scale
        X = self.p1_scaler.transform(df_row[self.p1_feats])

        # Failure probability (XGBoost)
        fail_prob = float(self.xgb_cls.predict_proba(X)[0, 1])

        rul_cycles = max(
         5,
       int((1.0 - fail_prob) * CONFIG["rul_cap"])
     )

        rul_km = round(rul_cycles * 20)

        # SHAP top sensors
        shap_vals   = self.explainer.shap_values(X)[0]
        top_sensors = get_top_sensors(shap_vals, self.p1_feats)

        # Failure mode (AI4I RF — approximate via sensor mapping)
        urgency = get_urgency(fail_prob, rul_cycles)

        # Recommendations
        recs = build_recommendations(top_sensors, rul_cycles, fail_prob)

        return {
            "vehicle_id":          vehicle_id,
            "predictions": {
                "rul_cycles":          int(rul_cycles),
                "rul_km_estimate":     rul_km,
                "failure_probability": round(fail_prob, 4),
                "urgency":             urgency,
            },
            "top_risk_sensors":    top_sensors,
            "recommendations":     recs,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 7. FASTAPI  (run independently after training)
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="Phase 3 — Predictive Maintenance API", version="1.0.0")

# Lazy-loaded engine (populated on first request)
_engine: PredictionEngine = None


def get_engine() -> PredictionEngine:
    global _engine
    if _engine is None:
        _engine = PredictionEngine.from_disk(CONFIG["models_dir"])
    return _engine


class SensorPayload(BaseModel):
    vehicle_id:       str
    # Raw sensors (same as Phase 1 output columns)
    temperature:      float
    pressure:         float
    rpm:              float
    vibration:        float
    battery_voltage:  float
    battery_current:  float
    battery_temp:     float
    fault_count:      float
    # Phase 1 health scores (required — call Phase 1 API first)
    engine_health:    float
    battery_health:   float
    vehicle_health:   float
    ml_health_score:  float
    trip_readiness:   float
    health_class_id:  int


@app.post("/predict", summary="Predict failure probability and RUL")
def predict_endpoint(payload: SensorPayload):
    engine = get_engine()
    data   = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    vid    = data.pop("vehicle_id")
    result = engine.predict(vid, data)
    return result


@app.get("/")
def root():
    return {
        "service": "Predictive Maintenance API",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", summary="Service liveness / model-load check")
def health_check():
    """
    Reports whether the trained model ensemble has loaded successfully.
    Lazily loads the engine on first call (same as /predict), so a healthy
    response here guarantees /predict will not fail on missing artefacts.
    """
    try:
        get_engine()
    except Exception as exc:  # noqa: BLE001 - health check must never itself crash
        return {"status": "unhealthy", "models_loaded": False, "detail": str(exc)}
    return {"status": "healthy", "models_loaded": True}


# ══════════════════════════════════════════════════════════════════════════════
# 8. BATCH PREDICTION MODULE
# ══════════════════════════════════════════════════════════════════════════════

# Columns from Output.csv that are passed into engine.predict() as sensor_row
_SENSOR_COLS = [
    "temperature", "pressure", "rpm", "vibration",
    "battery_voltage", "battery_current", "battery_temp", "fault_count",
    "engine_health", "battery_health", "vehicle_health",
    "ml_health_score", "trip_readiness", "health_class_id",
]


def _derive_maintenance_priority(fail_prob: float, urgency: str) -> str:
    """Map failure probability + urgency to a human-friendly priority label."""
    if fail_prob >= 0.80 or urgency == "CRITICAL":
        return "Immediate"
    if fail_prob >= 0.55:
        return "High"
    if fail_prob >= 0.30:
        return "Medium"
    return "Low"


def _row_to_sensor_dict(row: pd.Series) -> dict:
    """Convert one DataFrame row into the sensor_row dict engine.predict() expects."""
    return {col: row[col] for col in _SENSOR_COLS}


def _flatten_result(vehicle_id: str, row: pd.Series, result: dict) -> dict:
    """Merge Phase 1 passthrough values with prediction result into a flat dict."""
    preds      = result["predictions"]
    sensors    = result["top_risk_sensors"]
    recs       = result["recommendations"]
    fail_prob  = preds["failure_probability"]
    urgency    = preds["urgency"]
    top_sensor = sensors[0] if sensors else {}
    top_rec    = recs[0]    if recs    else {}

    return {
        # ── Identifiers ───────────────────────────────────────────────────────
        "Vehicle_ID":                   vehicle_id,
        # ── Phase 1 passthrough ───────────────────────────────────────────────
        "Engine_Health":                row.get("engine_health"),
        "Battery_Health":               row.get("battery_health"),
        "Vehicle_Health":               row.get("vehicle_health"),
        "ML_Health_Score":              row.get("ml_health_score"),
        "Trip_Readiness":               row.get("trip_readiness"),
        # ── Predictions ───────────────────────────────────────────────────────
        "Failure_Probability":          round(fail_prob, 4),
        "Failure_Risk_Percentage":      f"{round(fail_prob * 100, 1)}%",
        "Urgency":                      urgency,
        "Remaining_Useful_Life_Cycles": preds["rul_cycles"],
        "Remaining_Useful_Life_KM":     preds["rul_km_estimate"],
        # ── Top risk sensor (SHAP) ────────────────────────────────────────────
        "Top_Risk_Sensor":              top_sensor.get("sensor", "N/A"),
        "Top_Risk_SHAP_Value":          top_sensor.get("shap_value", 0.0),
        # ── Top recommendation ────────────────────────────────────────────────
        "Affected_System":              top_rec.get("system", "N/A"),
        "Recommended_Action":           top_rec.get("action", "N/A"),
        "Reason":                       top_rec.get("reason", "N/A"),
        "Book_Service_Within_Days":     top_rec.get("book_within_days", "N/A"),
        # ── Derived ───────────────────────────────────────────────────────────
        "Maintenance_Priority":         _derive_maintenance_priority(fail_prob, urgency),
        "Prediction_Timestamp":         pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def batch_predict(
    engine: "PredictionEngine",
    csv_path: str,
    output_path: str = "outputs/Phase3_Predictions.csv",
) -> pd.DataFrame:
    """
    Run predictions for every row in csv_path and save results to output_path.

    Parameters
    ----------
    engine      : Trained PredictionEngine instance.
    csv_path    : Path to Phase 1 Output.csv.
    output_path : Destination CSV (folder created automatically if missing).

    Returns
    -------
    pd.DataFrame containing all prediction rows (same content as saved CSV).
    """
    # ── Load input CSV ────────────────────────────────────────────────────────
    df_input = pd.read_csv(csv_path)
    total    = len(df_input)
    print(f"\n[Batch] Loaded {total:,} vehicles from '{csv_path}'")

    # ── Validate required columns are present ─────────────────────────────────
    missing_cols = [c for c in _SENSOR_COLS if c not in df_input.columns]
    if missing_cols:
        raise ValueError(f"[Batch] Input CSV is missing required columns: {missing_cols}")

    # ── Resolve Vehicle IDs ───────────────────────────────────────────────────
    id_candidates  = ["vehicle_id", "Vehicle_ID", "id", "ID", "VehicleID"]
    existing_id    = next((c for c in id_candidates if c in df_input.columns), None)
    if existing_id:
        vehicle_ids = df_input[existing_id].astype(str).tolist()
        print(f"[Batch] Using existing ID column: '{existing_id}'")
    else:
        vehicle_ids = [f"Vehicle_{i + 1:04d}" for i in range(total)]
        print("[Batch] No ID column found — generating Vehicle_0001 … style IDs")

    # ── Predict row by row ────────────────────────────────────────────────────
    records, skipped = [], 0

    for idx, (_, row) in enumerate(df_input.iterrows()):
        vid = vehicle_ids[idx]
        try:
            sensor_dict = _row_to_sensor_dict(row)
            result      = engine.predict(vid, sensor_dict)
            records.append(_flatten_result(vid, row, result))
        except Exception as exc:
            skipped += 1
            print(f"  ⚠  Warning: skipped {vid} (row {idx}) — {exc}")
            continue

        # Progress indicator every 200 rows
        if (idx + 1) % 200 == 0 or (idx + 1) == total:
            print(f"  [{idx + 1:>4}/{total}] processed …")

    # ── Assemble & save DataFrame ─────────────────────────────────────────────
    df_out   = pd.DataFrame(records)
    out_dir  = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    df_out.to_csv(output_path, index=False)

    # ── Summary report ────────────────────────────────────────────────────────
    processed = len(df_out)
    counts    = df_out["Urgency"].value_counts().to_dict() if processed else {}
    avg_prob  = df_out["Failure_Probability"].mean() * 100 if processed else 0.0
    avg_rul   = df_out["Remaining_Useful_Life_Cycles"].mean() if processed else 0.0

    print("\n" + "=" * 44)
    print("  Batch Prediction Summary")
    print("=" * 44)
    print(f"  Vehicles Processed : {processed:>6,}")
    if skipped:
        print(f"  Rows Skipped       : {skipped:>6,}")
    print(f"  Critical           : {counts.get('CRITICAL', 0):>6,}")
    print(f"  High               : {counts.get('HIGH',     0):>6,}")
    print(f"  Medium             : {counts.get('MEDIUM',   0):>6,}")
    print(f"  Low                : {counts.get('LOW',      0):>6,}")
    print(f"  Avg Failure Prob   : {avg_prob:>5.1f}%")
    print(f"  Avg RUL            : {avg_rul:>5.1f} cycles")
    print(f"  CSV Saved At       : {output_path}")
    print("=" * 44 + "\n")

    return df_out


# ══════════════════════════════════════════════════════════════════════════════
# 9. ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        # ── Serve the API (models must already be trained) ────────────────────
        print("Starting FastAPI server on http://0.0.0.0:8000")
        uvicorn.run("phase2_pipeline:app", host="0.0.0.0", port=8000, reload=False)
    else:
        # ── Train all models ──────────────────────────────────────────────────
        models = run_pipeline()

        # ── Quick inference demo ──────────────────────────────────────────────
        print("\n── Demo prediction ──────────────────────────────────────")
        engine = PredictionEngine(models)
        sample = {
            "temperature": 105.0, "pressure": 35.0, "rpm": 3800.0,
            "vibration": 0.55, "battery_voltage": 12.1, "battery_current": 70.0,
            "battery_temp": 50.0, "fault_count": 8.0,
            "engine_health": 52.0, "battery_health": 65.0, "vehicle_health": 58.0,
            "ml_health_score": 12.0, "trip_readiness": 55.0, "health_class_id": 2,
        }
        result = engine.predict("TXL-8821", sample)
        print(json.dumps(result, indent=2))

        # ── Batch prediction over all Phase 1 rows ────────────────────────────
        batch_predict(
            engine      = engine,
            csv_path    = CONFIG["phase1_path"],
            output_path = "outputs/Phase3_Predictions.csv",
        )

        print("\nTo start the API server, run:")
        print("  python phase2_pipeline.py serve")
