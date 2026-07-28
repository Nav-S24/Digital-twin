"""
train_models.py
================
Trains and persists the two ML artefacts the Phase 2 API depends on:

  - failure_classifier.joblib  (XGBClassifier)  -> used to derive ml_health_score
  - rul_regressor.joblib       (XGBRegressor)   -> remaining useful life estimate

Run once (or whenever data/Output.csv changes):

    python train_models.py

These were never included in the original notebook deliverable - the
notebook only ever *defined* train_classifier.py / train_regressor.py as
Colab %%writefile cells and trained interactively, without persisting
the fitted models anywhere durable. Without saved model artefacts, no
API can serve ml_health_score or a RUL prediction without retraining on
every request, so this script closes that gap.
"""

from __future__ import annotations

import pandas as pd

from src.config import DATA_DIR
from src.train_classifier import save_classifier, train_failure_classifier
from src.train_regressor import prepare_rul_target, save_regressor, train_rul_regressor
from src.utils import get_logger

logger = get_logger(__name__)


def main() -> None:
    df = pd.read_csv(DATA_DIR / "Output.csv")
    logger.info("Loaded training data: %d rows", len(df))

    logger.info("Training failure classifier ...")
    clf, clf_metrics = train_failure_classifier(df)
    save_classifier(clf)
    logger.info("Classifier metrics: %s", clf_metrics)

    logger.info("Training RUL regressor ...")
    df_rul = prepare_rul_target(df)
    reg, reg_metrics = train_rul_regressor(df_rul)
    save_regressor(reg)
    logger.info("Regressor metrics: %s", reg_metrics)

    print("\nDone. Models saved to models/failure_classifier.joblib and models/rul_regressor.joblib")
    print(f"Classifier: precision={clf_metrics['precision']:.3f} recall={clf_metrics['recall']:.3f} "
          f"f1={clf_metrics['f1']:.3f} roc_auc={clf_metrics['roc_auc']:.3f}")
    print(f"Regressor:  MAE={reg_metrics['mae']:.3f} RMSE={reg_metrics['rmse']:.3f} R2={reg_metrics['r2']:.3f} "
          f"(synthetic_rul={reg_metrics['synthetic_rul']})")


if __name__ == "__main__":
    main()
