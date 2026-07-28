from pathlib import Path
from typing import Optional
import joblib, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, seaborn as sns
from sklearn.metrics import (classification_report, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from xgboost import XGBClassifier
from src.config import *
from src.utils import get_logger

logger = get_logger(__name__)
_EXCLUDE = {"timestamp","failure","health_class","health_class_id","trip_readiness_label","ml_health_score"}

def get_feature_columns(df):
    return [c for c in df.select_dtypes(include=[np.number]).columns if c not in _EXCLUDE]

def train_failure_classifier(df):
    feature_cols = get_feature_columns(df)
    X = df[feature_cols].values
    y = df["failure"].values.astype(int)
    logger.info("Class dist — 0: %d  1: %d  (%.1f%% pos)", (y==0).sum(), (y==1).sum(), 100*y.mean())
    X_train,X_test,y_train,y_test = train_test_split(X,y,test_size=TEST_SIZE,
                                                      random_state=RANDOM_SEED, stratify=y)
    model = XGBClassifier(**XGBOOST_CLASSIFIER_PARAMS)
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)
    cv_scores = cross_val_score(model,X_train,y_train,cv=cv,scoring="roc_auc",n_jobs=-1)
    logger.info("CV ROC-AUC: %.4f ± %.4f", cv_scores.mean(), cv_scores.std())
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:,1]
    precision = precision_score(y_test,y_pred,zero_division=0)
    recall    = recall_score(y_test,y_pred,zero_division=0)
    f1        = f1_score(y_test,y_pred,zero_division=0)
    roc_auc   = roc_auc_score(y_test,y_proba)
    logger.info("Precision: %.4f  Recall: %.4f  F1: %.4f  ROC-AUC: %.4f", precision,recall,f1,roc_auc)
    # Save confusion matrix
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cm = confusion_matrix(y_test,y_pred)
        fig,ax = plt.subplots(figsize=(5,4))
        sns.heatmap(cm,annot=True,fmt="d",cmap="Blues",
                    xticklabels=["No Failure","Failure"],yticklabels=["No Failure","Failure"],ax=ax)
        ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
        ax.set_title("Failure Classifier — Confusion Matrix")
        fig.tight_layout(); fig.savefig(OUTPUT_DIR/"confusion_matrix.png",dpi=120); plt.close(fig)
    except Exception as e:
        logger.warning("Could not save confusion matrix: %s", e)
    return model, {"precision":precision,"recall":recall,"f1":f1,"roc_auc":roc_auc,
                   "cv_roc_auc_mean":float(cv_scores.mean()),"feature_columns":feature_cols}

def add_ml_health_score(df, model):
    df = df.copy()
    X = df[get_feature_columns(df)].values
    df["ml_health_score"] = (100*(1 - model.predict_proba(X)[:,1])).clip(0,100)
    return df

def save_classifier(model, path=None):
    p = Path(path) if path else CLASSIFIER_MODEL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, p)
    logger.info("Classifier saved → %s", p)

def load_classifier(path=None):
    p = Path(path) if path else CLASSIFIER_MODEL_PATH
    return joblib.load(p)