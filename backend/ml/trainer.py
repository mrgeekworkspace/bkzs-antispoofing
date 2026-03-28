"""
Model Training Pipeline
Trains Random Forest (supervised) + Isolation Forest (unsupervised anomaly detection).
Saves models, scaler, and prints evaluation report.
"""
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
import logging

from .dataset_loader import FEATURE_COLS, LABEL_COL, LABEL_MAP, LABEL_MAP_INV, load_or_generate

logger = logging.getLogger(__name__)


def train(settings, data_dir: Path = None, dataset_type: str = "simulate",
          n_estimators_rf: int = 150, n_estimators_iso: int = 200,
          test_size: float = 0.2) -> dict:
    """
    Full training pipeline. Returns metrics dict.
    """
    logger.info("=== BKZS Anti-Spoofing Model Training ===")

    data_dir = data_dir or settings.DATA_RAW_DIR
    df = load_or_generate(data_dir, dataset_type)
    logger.info(f"Dataset: {len(df)} samples. Classes: {df[LABEL_COL].value_counts().to_dict()}")

    X = df[FEATURE_COLS].values
    y = df[LABEL_COL].map(LABEL_MAP).values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    logger.info(f"Training Random Forest ({n_estimators_rf} trees)...")
    rf = RandomForestClassifier(
        n_estimators=n_estimators_rf,
        max_depth=14,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced'
    )
    rf.fit(X_train_s, y_train)

    logger.info(f"Training Isolation Forest ({n_estimators_iso} trees) on NOMINAL data only...")
    X_nominal = X_train_s[y_train == 0]
    iso = IsolationForest(
        n_estimators=n_estimators_iso,
        contamination=0.05,
        random_state=42,
        n_jobs=-1
    )
    iso.fit(X_nominal)

    y_pred = rf.predict(X_test_s)
    report = classification_report(
        y_test, y_pred,
        target_names=['NOMINAL', 'JAMMING', 'SPOOFING'],
        output_dict=True
    )

    cv_scores = cross_val_score(rf, X_train_s, y_train, cv=5, scoring='f1_macro', n_jobs=-1)

    feat_importance = dict(zip(FEATURE_COLS, rf.feature_importances_.tolist()))

    settings.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(rf, settings.RF_MODEL_PATH)
    joblib.dump(iso, settings.ISO_MODEL_PATH)
    joblib.dump(scaler, settings.SCALER_PATH)

    logger.info(f"Models saved to {settings.MODEL_DIR}")
    logger.info(f"\n{classification_report(y_test, y_pred, target_names=['NOMINAL','JAMMING','SPOOFING'])}")
    logger.info(f"CV F1 (macro): {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")

    return {
        "status": "success",
        "samples_trained": len(X_train),
        "samples_tested": len(X_test),
        "accuracy": round(float(report['accuracy']), 4),
        "cv_f1_mean": round(float(cv_scores.mean()), 4),
        "cv_f1_std": round(float(cv_scores.std()), 4),
        "class_report": report,
        "feature_importance": feat_importance,
        "dataset_type": dataset_type,
    }
