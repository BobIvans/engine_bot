#!/usr/bin/env python3
"""models/train_xgboost.py

Deterministic XGBoost training script for miniML.

Features:
- Time-series split (80/20 chronological, no shuffling)
- Fixed random seeds for reproducibility
- Imports FEATURE_KEYS_V2 from features/trade_features
- Saves model.json and metrics.json

Usage:
    python models/train_xgboost.py --dataset dataset.parquet --out-dir artifacts/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

# Ensure repo root is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import xgboost as xgb
from sklearn.metrics import precision_score, recall_score, roc_auc_score

from features.trade_features import FEATURE_KEYS_V2


EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_INTERNAL = 3


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_parquet(path: str) -> "pandas.DataFrame":
    """Load Parquet file using duckdb if available, fallback to pandas."""
    try:
        import duckdb
        con = duckdb.connect(database=":memory:")
        df = con.execute(f"SELECT * FROM read_parquet('{path}')").df()
        con.close()
        return df
    except Exception:
        pass
    
    # Fallback to pandas
    try:
        import pandas as pd
        return pd.read_parquet(path)
    except Exception as e:
        raise ImportError(
            "Neither duckdb nor pandas available. Install one: pip install duckdb pandas"
        )


def train_xgboost(
    dataset_path: str,
    out_dir: str,
    target_roi_pct: float = 0.0,
) -> Dict[str, Any]:
    """Train XGBoost classifier and save artifacts.
    
    Args:
        dataset_path: Path to input Parquet file.
        out_dir: Directory to save model.json and metrics.json.
        target_roi_pct: Threshold for positive class (ROI > threshold).
    
    Returns:
        Dictionary containing metrics.
    """
    # Load data
    _eprint(f"Loading dataset from {dataset_path}...")
    df = load_parquet(dataset_path)
    
    if df.empty:
        raise ValueError("Dataset is empty")
    
    # Time-series split: sort by timestamp first
    if "ts" not in df.columns:
        raise ValueError("Dataset must contain 'ts' column for time-series split")
    
    df = df.sort_values("ts").reset_index(drop=True)
    _eprint(f"Dataset loaded: {len(df)} rows, sorted by ts")
    
    # Define target: positive if ROI > threshold
    y = (df["y_roi_horizon_pct"] > target_roi_pct).astype(int)
    _eprint(f"Target distribution: {y.sum()} positive / {len(y) - y.sum()} negative")
    
    # Select features using FEATURE_KEYS_V2 contract
    missing_keys = [k for k in FEATURE_KEYS_V2 if k not in df.columns]
    if missing_keys:
        raise ValueError(f"Missing feature columns in dataset: {missing_keys}")
    
    X = df[FEATURE_KEYS_V2]
    _eprint(f"Features: {len(FEATURE_KEYS_V2)} columns from FEATURE_KEYS_V2")
    
    # Time-series split: 80% train, 20% test (no shuffling)
    train_size = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:train_size], X.iloc[train_size:]
    y_train, y_test = y.iloc[:train_size], y.iloc[train_size:]
    
    _eprint(f"Train: {len(X_train)} samples, Test: {len(X_test)} samples")
    
    # Handle edge case: if train or test is empty
    if len(X_train) == 0 or len(X_test) == 0:
        raise ValueError("Insufficient data for train/test split")
    
    # Train XGBoost classifier with fixed random state
    _eprint("Training XGBoost classifier...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss",
        verbosity=1,
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate on test set
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    
    # Calculate metrics
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    
    try:
        auc = roc_auc_score(y_test, y_pred_proba)
    except ValueError:
        auc = 0.0  # Handle case where only one class is present
    
    metrics = {
        "precision": float(precision),
        "recall": float(recall),
        "auc": float(auc),
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "target_roi_pct": float(target_roi_pct),
        "feature_keys": FEATURE_KEYS_V2,
    }
    
    _eprint(f"Metrics: precision={precision:.4f}, recall={recall:.4f}, auc={auc:.4f}")
    
    # Save artifacts
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    model_path = out_path / "model.json"
    model.save_model(str(model_path))
    _eprint(f"Model saved to {model_path}")
    
    metrics_path = out_path / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    _eprint(f"Metrics saved to {metrics_path}")
    
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train XGBoost classifier on miniML features dataset."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to input Parquet dataset (from export_training_dataset.py)",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Directory to save model.json and metrics.json",
    )
    parser.add_argument(
        "--target-roi-pct",
        type=float,
        default=0.0,
        help="ROI threshold for positive class (default: 0.0)",
    )
    
    args = parser.parse_args()
    
    try:
        train_xgboost(
            dataset_path=args.dataset,
            out_dir=args.out_dir,
            target_roi_pct=args.target_roi_pct,
        )
        print(f"Training complete. Artifacts saved to {args.out_dir}", file=sys.stderr)
        return EXIT_OK
    except ValueError as e:
        _eprint(f"ERROR: {e}")
        return EXIT_BAD_INPUT
    except Exception as e:
        _eprint(f"ERROR: {type(e).__name__}: {e}")
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
