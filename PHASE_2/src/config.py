from pathlib import Path

# Project root = the directory containing this src/ package (two levels up
# from src/config.py). Previously hardcoded to a Colab-only path
# ("/content/vehicle_health_engine"), which meant every path derived from
# ROOT_DIR silently pointed nowhere outside a Colab runtime.
ROOT_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
OUTPUT_DIR = ROOT_DIR / "outputs"

SCHEMA_COLUMNS = ["timestamp","temperature","pressure","rpm","vibration",
                  "battery_voltage","battery_current","battery_temp","fault_count","failure"]
SENSOR_COLUMNS = ["temperature","pressure","rpm","vibration",
                  "battery_voltage","battery_current","battery_temp","fault_count"]

SCALER_TYPE = "minmax"
OUTLIER_METHOD = "iqr"
OUTLIER_IQR_MULTIPLIER = 1.5
OUTLIER_ZSCORE_THRESHOLD = 3.0
ROLLING_WINDOW = 5

ENGINE_THRESHOLDS = {
    "temperature": {"optimal_max": 90.0, "warning": 100.0, "critical": 110.0},
    "pressure":    {"optimal_min": 25.0, "warning": 20.0,  "critical": 15.0},
    "rpm":         {"optimal_max": 4000.0,"warning": 5000.0,"critical": 6500.0},
    "vibration":   {"optimal_max": 0.3,  "warning": 0.6,   "critical": 1.0},
    "fault_count": {"warning": 3, "critical": 7},
}
ENGINE_PENALTY_WEIGHTS = {"temperature":20,"pressure":20,"rpm":20,"vibration":20,"fault_count":20}

BATTERY_THRESHOLDS = {
    "voltage": {"nominal": 12.6, "warning": 11.8, "critical": 11.0},
    "current": {"max_draw": 100.0, "warning": 80.0, "critical": 120.0},
    "temp":    {"optimal_max": 45.0, "warning": 55.0, "critical": 65.0},
}

VEHICLE_HEALTH_WEIGHTS = {"engine": 0.7, "battery": 0.3}

HEALTH_CLASS_MAP = [
    (90, "Excellent", 0),
    (75, "Good",      1),
    (60, "Warning",   2),
    (0,  "Critical",  3),
]

TRIP_READINESS_WEIGHTS = {"vehicle_health": 0.6, "battery_health": 0.2,
                           "fault_penalty": 0.2, "fault_multiplier": 10}
TRIP_READINESS_LABELS = [(70, "Ready"), (50, "Caution"), (0, "Not Recommended")]

TEST_SIZE   = 0.2
RANDOM_SEED = 42
CV_FOLDS    = 5

XGBOOST_CLASSIFIER_PARAMS = {
    "n_estimators": 200, "max_depth": 6, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "eval_metric": "logloss", "random_state": RANDOM_SEED,
}
XGBOOST_REGRESSOR_PARAMS = {
    "n_estimators": 200, "max_depth": 6, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8, "random_state": RANDOM_SEED,
}

OUTPUT_DATASET_PATH   = OUTPUT_DIR / "vehicle_health_dataset.csv"
CLASSIFIER_MODEL_PATH = MODELS_DIR / "failure_classifier.joblib"
REGRESSOR_MODEL_PATH  = MODELS_DIR / "rul_regressor.joblib"
SCALER_PATH           = MODELS_DIR / "feature_scaler.joblib"